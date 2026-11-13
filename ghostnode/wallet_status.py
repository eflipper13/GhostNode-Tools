"""Read-only wallet readiness reports shared by the CLI and dashboard."""

from __future__ import annotations

from typing import Any, Callable

from ghostnode.collectors.rpc import _call
from ghostnode.config import Config

WalletCall = Callable[[str, Config, str | None], tuple[Any, str | None]]


def _safe_message(error: str | None) -> str:
    if not error:
        return "Wallet RPC did not return a usable response"
    lowered = error.lower()
    if "auth" in lowered or "cookie" in lowered or "credential" in lowered:
        return "Wallet RPC access failed; authentication details are not shown"
    if "unavailable" in lowered or "timed out" in lowered:
        return "Wallet RPC is unavailable or timed out"
    return "Wallet RPC status could not be verified"


def _error_status(error: str | None) -> str:
    """Use actionable check states while keeping uncertainty in readiness."""
    lowered = (error or "").lower()
    return "FAIL" if any(token in lowered for token in ("auth", "cookie", "credential")) else "SKIP"


def wallet_status_report(config: Config, rpc_call: WalletCall | None = None) -> dict[str, Any]:
    """Return bounded wallet readiness without exposing balances or secrets."""
    call = rpc_call or (lambda method, cfg, wallet=None: _call(method, cfg, wallet=wallet))
    wallets, error = call("listwallets", config, None)
    base = {
        "wallet_name": config.wallet_name,
        "wallet_functionality": "UNKNOWN",
        "wallet_loaded": "UNKNOWN",
        "readiness": "WALLET_STATUS_UNKNOWN",
        "staking_monitoring": "UNKNOWN",
        "node_monitoring": "UNKNOWN",
    }
    if error:
        return {"status": _error_status(error), "message": _safe_message(error), "data": base}
    if not isinstance(wallets, list):
        return {"status": "SKIP", "message": "Wallet list response was not usable", "data": base}
    base["wallet_functionality"] = "AVAILABLE"
    if config.wallet_name not in wallets:
        base.update({"wallet_loaded": False, "readiness": "WALLET_NOT_LOADED",
                     "node_monitoring": "NODE_ONLY_READY", "staking_monitoring": "NODE_ONLY_READY"})
        return {"status": "WARN", "message": "Configured wallet is not loaded; node-only monitoring remains available", "data": base}

    info, error = call("getwalletinfo", config, config.wallet_name)
    if error or not isinstance(info, dict):
        base.update({"wallet_loaded": True, "readiness": "WALLET_STATUS_UNKNOWN",
                     "node_monitoring": "NODE_ONLY_READY"})
        return {"status": _error_status(error), "message": _safe_message(error), "data": base}

    base.update({"wallet_loaded": True, "readiness": "WALLET_READY",
                 "node_monitoring": "NODE_ONLY_READY"})
    staking, staking_error = call("getstakinginfo", config, config.wallet_name)
    if staking_error or not isinstance(staking, dict):
        base["staking_monitoring"] = "UNKNOWN"
        return {"status": "WARN", "message": "Wallet is available; wallet-specific staking readiness is unknown", "data": base}
    base["staking_monitoring"] = "STAKING_MONITORING_READY"
    return {"status": "PASS", "message": "Wallet and wallet-specific staking monitoring are ready", "data": base}
