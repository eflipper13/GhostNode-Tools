from typing import Any

from ghostnode.collectors.rpc import _call
from ghostnode.config import Config
from ghostnode.models.results import Result, Status


def collect_wallet(config: Config, wallet_name: str = "ghostmain") -> Result:
    """Read wallet metadata and balance without loading, unlocking, or transacting."""
    wallets, error = _call("listwallets", config)
    base = {"wallet_name": wallet_name, "loaded": False, "balance": None, "encryption": None}
    if error:
        return Result(Status.UNKNOWN, base, error)
    if not isinstance(wallets, list):
        return Result(Status.UNKNOWN, base, "RPC returned an unexpected wallet list")
    if wallet_name not in wallets:
        return Result(Status.WARN, base, "Wallet is NOT LOADED")
    info, error = _call("getwalletinfo", config, wallet=wallet_name)
    if error:
        return Result(Status.UNKNOWN, {**base, "loaded": True}, error)
    if not isinstance(info, dict):
        return Result(Status.UNKNOWN, {**base, "loaded": True}, "RPC returned unexpected wallet data")
    unlocked_until = info.get("unlocked_until")
    encryption = "locked" if unlocked_until == 0 else "unlocked" if isinstance(unlocked_until, (int, float)) else None
    data: dict[str, Any] = {
        "wallet_name": info.get("walletname", wallet_name),
        "loaded": True,
        "balance": info.get("balance"),
        "encryption": info.get("encryptionstatus", encryption),
        "balances": None,
    }
    balances, balance_error = _call("getbalances", config, wallet=wallet_name)
    if isinstance(balances, dict):
        data["balances"] = balances
    if balance_error:
        return Result(Status.WARN, data, "Wallet balance categories unavailable")
    if data["balance"] is None and data["balances"] is None:
        return Result(Status.WARN, data, "Wallet balance is unavailable")
    return Result(Status.OK, data)
