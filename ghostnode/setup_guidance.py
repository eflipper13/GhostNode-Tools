"""Dry-run Ghost Core setup guidance; this module never changes system state."""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from ghostnode.config import Config
from ghostnode.doctor import _cli_available


def setup_report(config: Config) -> dict[str, Any]:
    local_cli = _cli_available(config.cli_path)
    local_datadir = Path(config.datadir).expanduser().is_dir()
    return {
        "status": "PASS" if local_cli or config.rpc_host else "WARN",
        "mode": "remote_rpc" if config.rpc_host else "local_or_remote_guidance",
        "environment": {"system": platform.system(), "architecture": platform.machine(),
                        "python": platform.python_version()},
        "ghost_core": {
            "local_cli_available": local_cli,
            "local_datadir_available": local_datadir,
            "remote_rpc_configured": bool(config.rpc_host),
        },
        "actions": [
            "Review the official Ghost Core distribution and verification instructions manually.",
            "Keep Ghost Core data and wallet files outside the GhostNode Tools directory.",
            "Use local RPC or a protected remote RPC endpoint; never expose RPC publicly.",
            "No installer, download, permission change, service change, or configuration write was performed.",
        ],
        "limitations": [
            "Official distribution URLs, checksums, and signatures were not verified by this dry-run.",
            "Wallet creation, loading, unlocking, and backup guidance are deferred to M2.",
        ],
    }
