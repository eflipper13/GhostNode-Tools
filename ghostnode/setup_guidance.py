"""Dry-run Ghost Core setup guidance; this module never changes system state."""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from ghostnode.config import Config
from ghostnode.doctor import _cli_available
from ghostnode.wallet_location import detect_wallet_location


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


def wallet_setup_report(config: Config | None = None) -> dict[str, Any]:
    """Return English-only, non-operational wallet setup guidance."""
    config = config or Config()
    return {
        "status": "PASS",
        "mode": "guidance_only",
        "wallet_location": detect_wallet_location(config),
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
        "backup": {
            "status": "GUIDANCE_AVAILABLE",
            "why": "A wallet backup is essential because loss of wallet data or key material can permanently prevent recovery of funds.",
            "guidance": [
                "Back up the wallet files or wallet directory required by the exact Ghost Core wallet layout; do not assume every wallet is a single wallet.dat file.",
                "Do not copy a live wallet database unless Ghost Core's supported backup procedure explicitly permits it.",
                "Use Ghost Core's official backup method after verifying its version-specific documentation; no unverified command is generated here.",
                "Store encrypted backups offline, separately from the running node, and consider multiple independent protected copies.",
                "Refresh backups when wallet state or key material changes, and record which Ghost Core version created them.",
            ],
            "verification": "GhostNode Tools does not create, copy, or automatically verify backups. BACKUP_VERIFIED requires a separately verified recovery or integrity procedure.",
        },
        "passphrase": {
            "status": "GUIDANCE_AVAILABLE",
            "guidance": [
                "Encrypt wallets using Ghost Core's official procedure.",
                "Use a strong, unique passphrase stored in a trusted password manager or secure offline record.",
                "Keep the passphrase separate from wallet backups.",
                "A forgotten encryption passphrase may make funds unrecoverable; GhostNode Tools cannot recover it.",
            ],
        },
        "recovery": {
            "status": "GUIDANCE_AVAILABLE",
            "guidance": [
                "Stop and preserve the existing node and wallet before attempting recovery.",
                "Restore only from a valid backup into an isolated, version-compatible Ghost Core data location.",
                "Never overwrite an existing wallet; make a separate copy and follow Ghost Core's official restoration procedure.",
                "After disk or system failure, verify the restored wallet using Ghost Core's documented checks before relying on it.",
                "An encrypted wallet can be used only when its passphrase is available; a lost passphrase is not guaranteed recoverable.",
            ],
            "commands": "No version-specific restoration command is shown because it was not verified against official Ghost Core documentation.",
        },
        "checklist": [
            {"item": "Wallet location identified or explicitly unknown", "status": "GUIDANCE_AVAILABLE"},
            {"item": "Encryption guidance available", "status": "GUIDANCE_AVAILABLE"},
            {"item": "Secure backup guidance available", "status": "GUIDANCE_AVAILABLE"},
            {"item": "Recovery procedure available", "status": "GUIDANCE_AVAILABLE"},
            {"item": "Passphrase loss risks explained", "status": "GUIDANCE_AVAILABLE"},
        ],
        "limitations": [
            "No wallet-changing RPC command is generated or executed.",
            "Ghost Core wallet-creation command syntax was not asserted because it was not verified from an official source in this repository.",
            "GUIDANCE_REVIEWED requires explicit user acknowledgement; BACKUP_REPORTED_BY_USER and BACKUP_VERIFIED are never claimed automatically.",
        ],
    }
