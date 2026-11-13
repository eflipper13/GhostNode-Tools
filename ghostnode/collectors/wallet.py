from typing import Any

from ghostnode.collectors.rpc import _call
from ghostnode.config import Config
from ghostnode.models.results import Result, Status


def collect_wallet(config: Config, wallet_name: str | None = None) -> Result:
    """Read wallet metadata and balance without loading, unlocking, or transacting."""
    wallet_name = wallet_name or config.wallet_name
    wallets, error = _call("listwallets", config)
    base = {"wallet_name": wallet_name, "loaded": False, "balance": None, "encryption": None,
            "readiness": "WALLET_STATUS_UNKNOWN", "monitoring_mode": "NODE_ONLY_READY"}
    if error:
        return Result(Status.UNKNOWN, base, error)
    if not isinstance(wallets, list):
        return Result(Status.UNKNOWN, base, "RPC returned an unexpected wallet list")
    if wallet_name not in wallets:
        return Result(Status.WARN, {**base, "readiness": "WALLET_NOT_LOADED"}, "Wallet is NOT LOADED")
    info, error = _call("getwalletinfo", config, wallet=wallet_name)
    if error:
        return Result(Status.UNKNOWN, {**base, "loaded": True, "readiness": "WALLET_STATUS_UNKNOWN"}, error)
    if not isinstance(info, dict):
        return Result(Status.UNKNOWN, {**base, "loaded": True, "readiness": "WALLET_STATUS_UNKNOWN"}, "RPC returned unexpected wallet data")
    unlocked_until = info.get("unlocked_until")
    encryption = "locked" if unlocked_until == 0 else "unlocked" if isinstance(unlocked_until, (int, float)) else None
    data: dict[str, Any] = {
        "wallet_name": info.get("walletname", wallet_name),
        "loaded": True,
        "readiness": "WALLET_READY",
        "monitoring_mode": "STAKING_MONITORING_PENDING",
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
