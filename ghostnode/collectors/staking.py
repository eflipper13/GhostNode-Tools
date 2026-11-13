from typing import Any
import math

from ghostnode.collectors.rpc import _call
from ghostnode.config import Config
from ghostnode.models.results import Result, Status


CAUSES = {
    "low_balance": "Not enough stakeable balance",
    "low_depth": "Funds have not reached staking depth",
    "locked": "Wallet is locked",
    "limited": "Staking is limited",
    "disabled": "Staking is disabled",
}


def _probability(expected_time: Any, seconds: int) -> float | None:
    """Poisson estimate from the node's expected time; never a guarantee."""
    if not _finite_nonnegative(expected_time, strictly_positive=True):
        return None
    return round((1 - math.exp(-seconds / expected_time)) * 100, 2)


def _finite_nonnegative(value: Any, strictly_positive: bool = False) -> bool:
    """Accept real finite numbers only; bool is deliberately not numeric input."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    return value > 0 if strictly_positive else value >= 0


def _number(value: Any, strictly_positive: bool = False) -> float | int | None:
    return value if _finite_nonnegative(value, strictly_positive) else None


def collect_staking(config: Config, loaded: bool) -> Result:
    data: dict[str, Any] = {"enabled": None, "staking": None, "cause": None, "wallet_weight": None, "network_weight": None, "expected_time": None, "minstakeabledepth": None, "difficulty": None, "percent_year_reward": None}
    public, public_error = _call("getposdifficulty", config)
    if isinstance(public, dict):
        data["network_weight"] = _number(public.get("netstakeweight"))
        data["difficulty"] = _number(public.get("difficulty"))
    if not loaded:
        return Result(Status.WARN if public_error is None else Status.UNKNOWN, data, "Wallet is NOT LOADED")
    info, info_error = _call("getstakinginfo", config, wallet="ghostmain")
    if isinstance(info, dict):
        data.update({
            "enabled": info.get("enabled"),
            "staking": info.get("staking"),
            "cause": info.get("cause"),
            "cause_description": CAUSES.get(info.get("cause")),
            "wallet_weight": _number(info.get("weight")),
            "network_weight": _number(info.get("netstakeweight"),) if "netstakeweight" in info else data["network_weight"],
            "expected_time": _number(info.get("expectedtime"), strictly_positive=True),
            "minstakeabledepth": _number(info.get("minstakeabledepth")),
            "difficulty": _number(info.get("difficulty")) if "difficulty" in info else data["difficulty"],
            "percent_year_reward": _number(info.get("percentyearreward")),
        })
    errors = [error for error in (public_error, info_error) if error]
    if errors:
        return Result(Status.UNKNOWN, data, "Staking RPC unavailable")
    wallet_weight = data.get("wallet_weight")
    network_weight = data.get("network_weight")
    share = None
    if isinstance(wallet_weight, (int, float)) and isinstance(network_weight, (int, float)) and network_weight > 0:
        share = round(wallet_weight / network_weight * 100, 6)
    expected_time = data.get("expected_time")
    data["intelligence"] = {
        "wallet_share_percent": share,
        "probability_24h_percent": _probability(expected_time, 86400),
        "probability_7d_percent": _probability(expected_time, 604800),
        "probability_30d_percent": _probability(expected_time, 2592000),
        "historical_data_available": False,
        "history_note": "Historical staking data is not exposed by the current read-only RPC set.",
    }
    if data["staking"] is False:
        return Result(Status.WARN, data, data.get("cause_description") or "Staking is inactive")
    return Result(Status.OK, data)
