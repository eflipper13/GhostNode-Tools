"""Read-only Ghost Core detection and diagnostics for the v0.2.0 M1 milestone."""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ghostnode.collectors.rpc import _call, _format_version
from ghostnode.config import Config

RpcCall = Callable[[str, Config], tuple[Any, str | None]]
KNOWN_VERSIONS = {"0.23.1.0"}


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    message: str
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        result = {"name": self.name, "status": self.status, "message": self.message}
        if self.details:
            result["details"] = self.details
        return result


def _cli_available(path: str) -> bool:
    expanded = Path(path).expanduser()
    if "/" in path:
        return expanded.is_file() and expanded.stat().st_mode & 0o111 != 0
    return shutil.which(path) is not None


def _rpc_error_message(error: str | None) -> str:
    if not error:
        return "RPC request did not return a response"
    lowered = error.lower()
    if "timed out" in lowered or "unavailable" in lowered:
        return "Ghost Core RPC endpoint is unreachable or the CLI is unavailable"
    if "authentication" in lowered or "cookie" in lowered:
        return "Ghost Core RPC request failed; check endpoint access and authentication"
    if "failed" in lowered:
        return "Ghost Core RPC request failed; check endpoint access and authentication"
    return "Ghost Core RPC request failed"


class GhostCoreDoctor:
    """Collect bounded, non-mutating checks using the existing RPC client."""

    def __init__(self, config: Config, expected_network: str = "main",
                 rpc_call: RpcCall | None = None) -> None:
        self.config = config
        self.expected_network = expected_network
        self.rpc_call = rpc_call or (lambda method, cfg: _call(method, cfg))
        self._responses: dict[str, Any] = {}
        self._errors: dict[str, str | None] = {}

    def _get(self, method: str) -> Any:
        if method not in self._responses and method not in self._errors:
            value, error = self.rpc_call(method, self.config)
            if error:
                self._errors[method] = error
            else:
                self._responses[method] = value
        return self._responses.get(method)

    def run(self) -> list[Check]:
        checks = [self._environment(), self._local_cli(), self._configuration()]
        blockchain = self._get("getblockchaininfo")
        network = self._get("getnetworkinfo")
        staking = self._get("getstakinginfo")
        checks.extend((self._rpc_status(), self._version(network), self._network(blockchain),
                       self._synchronization(blockchain), self._staking(staking),
                       self._access(blockchain)))
        return checks

    def _environment(self) -> Check:
        return Check("environment", "PASS", "Operating system and architecture detected",
                     {"system": platform.system(), "release": platform.release(),
                      "architecture": platform.machine(), "python": platform.python_version()})

    def _local_cli(self) -> Check:
        if _cli_available(self.config.cli_path):
            return Check("local_cli", "PASS", "Configured Ghost Core CLI is executable")
        if self.config.rpc_host:
            return Check("local_cli", "SKIP", "No local CLI was found; using configured remote RPC guidance")
        return Check("local_cli", "FAIL", "Configured Ghost Core CLI is not available")

    def _configuration(self) -> Check:
        if self.config.rpc_host:
            if self.config.rpc_port is None:
                return Check("configuration", "WARN", "Remote RPC host is set but no RPC port is configured")
            return Check("configuration", "WARN",
                         "Remote RPC is configured; protect credentials and never expose RPC publicly",
                         {"host_configured": True, "port_configured": True})
        datadir = Path(self.config.datadir).expanduser()
        if datadir.is_dir() and datadir.exists():
            return Check("configuration", "PASS", "Local Ghost Core data directory is available")
        return Check("configuration", "WARN", "Local Ghost Core data directory is not available")

    def _rpc_status(self) -> Check:
        errors = [self._errors.get(method) for method in
                  ("getblockchaininfo", "getnetworkinfo", "getstakinginfo")]
        errors = [error for error in errors if error]
        if errors:
            return Check("rpc", "FAIL", _rpc_error_message(errors[0]))
        return Check("rpc", "PASS", "Required read-only Ghost Core RPC methods responded")

    def _version(self, network: Any) -> Check:
        if not isinstance(network, dict):
            return Check("version", "SKIP", "Ghost Core version was not reported")
        version = _format_version(network.get("version"), network.get("subversion"))
        if not version:
            return Check("version", "WARN", "Ghost Core version is unknown")
        if version not in KNOWN_VERSIONS:
            return Check("version", "WARN", "Ghost Core version is not in the validated compatibility set")
        return Check("version", "PASS", "Ghost Core version was identified", {"version": version})

    def _network(self, blockchain: Any) -> Check:
        if not isinstance(blockchain, dict) or not blockchain.get("chain"):
            return Check("network", "SKIP", "Network mode was not reported")
        chain = blockchain["chain"]
        if chain != self.expected_network:
            return Check("network", "FAIL", "Ghost Core is using an unexpected network mode")
        return Check("network", "PASS", "Ghost Core network mode matches the expected mode",
                     {"network": chain})

    def _synchronization(self, blockchain: Any) -> Check:
        if not isinstance(blockchain, dict):
            return Check("synchronization", "SKIP", "Synchronization state was not reported")
        if blockchain.get("initialblockdownload") is True:
            return Check("synchronization", "WARN", "Ghost Core is still synchronizing")
        blocks, headers = blockchain.get("blocks"), blockchain.get("headers")
        if not isinstance(blocks, int) or not isinstance(headers, int):
            return Check("synchronization", "WARN", "Synchronization height is unavailable")
        if blocks < headers:
            return Check("synchronization", "WARN", "Ghost Core is behind its reported headers")
        return Check("synchronization", "PASS", "Ghost Core reports a synchronized chain")

    def _staking(self, staking: Any) -> Check:
        if not isinstance(staking, dict):
            return Check("staking", "SKIP", "Staking state was not reported")
        if staking.get("enabled") is False:
            return Check("staking", "WARN", "Staking is disabled in the reported node state")
        return Check("staking", "PASS", "Staking state is available")

    def _access(self, blockchain: Any) -> Check:
        if self._errors.get("getblockchaininfo"):
            return Check("access", "FAIL", "The configured user cannot complete the read-only RPC preflight")
        if blockchain is not None:
            return Check("access", "PASS", "The configured user can complete the read-only preflight")
        return Check("access", "SKIP", "User access could not be evaluated")


def summarize(checks: list[Check]) -> str:
    statuses = {check.status for check in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "WARN"
    if all(check.status == "SKIP" for check in checks):
        return "SKIP"
    return "PASS"


def report_dict(checks: list[Check]) -> dict[str, Any]:
    return {"status": summarize(checks), "checks": [check.as_dict() for check in checks]}
