"""Read-only orchestration for the GhostNode Tools first-run experience."""

from __future__ import annotations

from typing import Any

from ghostnode.config import Config
from ghostnode.doctor import Check, GhostCoreDoctor
from ghostnode.setup_guidance import wallet_setup_report


def _status(checks: list[Check]) -> str:
    states = {check.status for check in checks}
    if "FAIL" in states:
        return "FAIL"
    if "WARN" in states:
        return "WARN"
    if states and states <= {"SKIP"}:
        return "SKIP"
    return "PASS"


def _stage(name: str, checks: list[Check], message: str) -> dict[str, Any]:
    return {"name": name, "status": _status(checks), "message": message,
            "checks": [check.as_dict() for check in checks]}


def _redacted_location(location: dict[str, Any]) -> dict[str, Any]:
    """Keep first-run output useful without exposing local filesystem paths."""
    return {"status": location.get("status"), "scope": location.get("scope"),
            "path": None, "message": location.get("message")}


def first_run_report(config: Config, expected_network: str = "main",
                     rpc_call=None, network_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run existing diagnostics once and compose actionable first-run stages."""
    checks = GhostCoreDoctor(config, expected_network=expected_network,
                             rpc_call=rpc_call).run()
    by_name = {check.name: check for check in checks}
    wallet_check = by_name["wallet"]
    wallet_details = wallet_check.details or {}
    wallet_setup = wallet_setup_report(config)

    if config.rpc_host:
        mode = "REMOTE_NODE"
    elif wallet_details.get("readiness") in {"WALLET_READY", "STAKING_MONITORING_READY"}:
        mode = "LOCAL_WALLET"
    else:
        mode = "NODE_ONLY"

    environment = [by_name[name] for name in ("environment", "local_cli", "configuration")]
    rpc = [by_name[name] for name in ("rpc", "network", "access", "version")]
    sync = [by_name["synchronization"]]
    staking = [by_name["staking"], wallet_check]
    stages = [
        _stage("environment", environment, "Environment and Ghost Core configuration were checked."),
        _stage("rpc", rpc, "Read-only RPC connectivity and expected network were checked."),
        _stage("wallet", [wallet_check], "Wallet availability was checked without changing wallet state."),
        {"name": "wallet_security", "status": "WARN",
         "message": "Security, backup, passphrase, and recovery guidance is available but not acknowledged.",
         "details": {"backup_status": "GUIDANCE_AVAILABLE",
                      "backup_verified": False,
                      "wallet_location": _redacted_location(wallet_setup["wallet_location"])}},
        _stage("staking", staking + sync,
               "Staking readiness is reported from available node and wallet diagnostics."),
        {"name": "dashboard", "status": "PASS",
         "message": "The read-only dashboard is available on its configured interface after explicit operator review.",
         "details": {"bind": "127.0.0.1", "mutating_actions": False,
                     "network": network_plan or {"mode": "localhost", "restart_required": True}}},
    ]
    statuses = {stage["status"] for stage in stages}
    overall = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
    next_steps: list[str] = []
    if by_name["rpc"].status == "FAIL":
        next_steps.append("Resolve the read-only Ghost Core RPC or authentication issue, then rerun ghostnode init.")
    if wallet_details.get("readiness") == "WALLET_NOT_LOADED":
        next_steps.append("Use ghostnode wallet setup for guidance, or continue safely in NODE_ONLY mode.")
    elif wallet_details.get("readiness") == "WALLET_STATUS_UNKNOWN":
        next_steps.append("Review wallet RPC availability; do not infer wallet absence from this result.")
    next_steps.append("Run ghostnode doctor --json for detailed node checks.")
    next_steps.append("Run ghostnode wallet status --json for detailed wallet readiness.")
    next_steps.append("Run ghostnode wallet setup --json for backup and recovery guidance.")
    next_steps.append("Review dashboard network settings, then start ghostnode web with the explicit approved mode.")
    return {
        "status": overall,
        "mode": mode,
        "stages": stages,
        "next_steps": next_steps,
        "security": {
            "read_only": True,
            "wallet_state_changed": False,
            "filesystem_written": False,
            "backup_status": "GUIDANCE_AVAILABLE",
        },
        "network": network_plan or {"mode": "localhost", "lan_address": None,
                                     "port": 44678, "restart_required": True,
                                     "applied": False},
    }
