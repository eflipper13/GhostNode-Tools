"""Conservative wallet location metadata; never opens wallet storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ghostnode.config import Config


def detect_wallet_location(config: Config) -> dict[str, Any]:
    """Find a wallet path only when filesystem metadata makes it unambiguous.

    This function uses ``is_file``/``is_dir`` only. It never reads wallet
    databases, follows wallet contents, or probes a remote filesystem.
    """
    if config.rpc_host:
        return {
            "status": "WALLET_PATH_UNKNOWN",
            "scope": "remote",
            "path": None,
            "message": "The wallet is on a remote RPC node; its filesystem path is not exposed or inspected.",
        }

    datadir = Path(config.datadir).expanduser()
    if not datadir.is_dir():
        return {
            "status": "WALLET_PATH_UNKNOWN",
            "scope": "local",
            "path": None,
            "message": "The configured local Ghost Core data directory is not available.",
        }

    candidates: list[Path] = []
    if config.wallet_dir:
        wallet_dir = Path(config.wallet_dir).expanduser()
        explicit = wallet_dir / config.wallet_name
        if explicit.is_dir():
            candidates.append(explicit)
    else:
        # These are metadata checks for known Ghost Core layouts, not guesses.
        for candidate in (datadir / "wallets" / config.wallet_name,
                          datadir / config.wallet_name):
            if candidate.is_dir():
                candidates.append(candidate)
        legacy = datadir / "wallet.dat"
        if legacy.is_file():
            candidates.append(legacy)

    unique = list(dict.fromkeys(candidates))
    if len(unique) == 1:
        return {
            "status": "WALLET_PATH_FOUND_BY_METADATA",
            "scope": "local",
            "path": str(unique[0]),
            "message": "A matching wallet path was found by filesystem metadata only; wallet contents were not inspected.",
        }
    if len(unique) > 1:
        return {
            "status": "WALLET_PATH_UNKNOWN",
            "scope": "local",
            "path": None,
            "message": "Multiple possible wallet locations exist; no path was selected.",
        }
    return {
        "status": "WALLET_PATH_UNKNOWN",
        "scope": "local",
        "path": None,
        "message": "No supported wallet layout was confirmed; do not infer a wallet path.",
    }
