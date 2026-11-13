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
            "Wallet creation, loading, unlocking, and backup operations remain outside this dry-run.",
        ],
    }


def wallet_setup_report() -> dict[str, Any]:
    """Return English-only, non-operational wallet setup guidance."""
    return {
        "status": "PASS",
        "mode": "guidance_only",
        "options": [
            {"name": "Create a new wallet", "guidance": "Use Ghost Core's verified official wallet documentation and CLI on the node; GhostNode Tools does not generate, load, encrypt, or back up wallets."},
            {"name": "Use an existing wallet", "guidance": "Load and verify it using Ghost Core's own documented procedures, then run ghostnode wallet status. Never paste credentials into GhostNode Tools."},
            {"name": "Continue without a wallet", "guidance": "Node-only monitoring remains supported; wallet rewards and wallet-specific staking readiness will be unavailable."},
        ],
        "security": [
            "Encrypt wallets using Ghost Core's official procedure before holding funds.",
            "Create and verify secure backups outside the application directory; never copy active wallet files into this repository.",
            "Keep recovery credentials offline and plan recovery before relying on the wallet.",
            "Never disclose private keys, recovery phrases, wallet passwords, cookies, or RPC credentials.",
            "Local RPC is preferable; remote RPC must be protected and must not be exposed publicly.",
        ],
        "limitations": [
            "No wallet-changing RPC command is generated or executed.",
            "Ghost Core wallet-creation command syntax was not asserted because it was not verified from an official source in this repository.",
        ],
    }
