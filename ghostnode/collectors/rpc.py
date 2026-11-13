import json
import logging
import os
import re
import shutil
import subprocess
from typing import Any

from ghostnode.config import Config
from ghostnode.intelligence.diagnostics import sanitize_error
from ghostnode.models.results import Result, Status

_ALLOWED_METHODS = {"getblockchaininfo", "getnetworkinfo", "getpeerinfo", "listwallets", "getwalletinfo", "getbalances", "getstakinginfo", "getposdifficulty", "getblockhash", "getblock", "getblockreward", "listtransactions", "listunspent", "getrawtransaction", "gettxout", "getaddressinfo"}
_NO_ARGS = {"getblockchaininfo", "getnetworkinfo", "getpeerinfo", "listwallets", "getwalletinfo", "getbalances", "getstakinginfo", "getposdifficulty"}
LOG = logging.getLogger("ghostnode.rpc")


def _serialize_cli_arg(value: Any) -> str:
    """Serialize one typed ghost-cli argument without shell interpolation."""
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"unsupported RPC argument type: {type(value).__name__}")


def _validate_args(method: str, args: list[Any] | None) -> str | None:
    """Validate CLI RPC arguments before any subprocess is started."""
    if method in _NO_ARGS:
        return None if not args else "RPC method does not accept arguments"
    if method in {"getblockhash", "getblockreward"}:
        if len(args or []) != 1 or isinstance(args[0], bool) or not isinstance(args[0], int) or args[0] < 0:
            return "RPC argument must be a non-negative integer height"
    elif method == "getblock":
        if not 1 <= len(args or []) <= 3 or not isinstance(args[0], str) or not args[0]:
            return "getblock requires a block hash and optional verbosity arguments"
        if len(args or []) >= 2 and (isinstance(args[1], bool) or not isinstance(args[1], int) or args[1] not in (0, 1, 2)):
            return "getblock verbosity must be 0, 1, or 2"
        if len(args or []) == 3 and not isinstance(args[2], bool):
            return "getblock third argument must be boolean"
    elif method == "getrawtransaction":
        values = args or []
        if not 1 <= len(values) <= 3 or not isinstance(values[0], str) or not values[0]:
            return "getrawtransaction requires a transaction id and optional verbosity/block hash"
        if len(values) >= 2 and (isinstance(values[1], bool) or not isinstance(values[1], int) or values[1] not in (0, 1, 2)):
            return "getrawtransaction verbosity must be 0, 1, or 2"
        if len(values) == 3 and not isinstance(values[2], str):
            return "getrawtransaction block hash must be a string"
    elif method == "gettxout":
        values = args or []
        if not 2 <= len(values) <= 3:
            return "gettxout requires txid, vout, and optional include_mempool"
        if not isinstance(values[0], str) or not re.fullmatch(r"[0-9a-fA-F]{64}", values[0]):
            return "gettxout requires a valid transaction id"
        if isinstance(values[1], bool) or not isinstance(values[1], int) or values[1] < 0:
            return "gettxout vout must be a non-negative integer"
        if len(values) == 3 and not isinstance(values[2], bool):
            return "gettxout include_mempool must be boolean"
    elif method == "getaddressinfo":
        if len(args or []) != 1 or not isinstance(args[0], str) or not args[0]:
            return "getaddressinfo requires an address string"
    elif method == "listtransactions":
        values = args or []
        if len(values) != 3 or not isinstance(values[0], str) or not isinstance(values[1], int) or isinstance(values[1], bool) or not 1 <= values[1] <= 1000 or not isinstance(values[2], int) or isinstance(values[2], bool) or values[2] < 0:
            return "listtransactions requires account, count (1..1000), and non-negative skip"
    elif method == "listunspent":
        values = args or []
        if not 2 <= len(values) <= 5:
            return "listunspent requires minconf and maxconf, with optional addresses/options"
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values[:2]):
            return "listunspent confirmations must be non-negative integers"
        if values[0] > values[1]:
            return "listunspent minconf cannot exceed maxconf"
        if len(values) >= 3 and not isinstance(values[2], list):
            return "listunspent addresses must be an array"
        if len(values) >= 4 and not isinstance(values[3], bool):
            return "listunspent include_unsafe must be boolean"
        if len(values) == 5 and (isinstance(values[4], bool) or not isinstance(values[4], (int, float)) or values[4] < 0):
            return "listunspent minimum amount must be non-negative"
    return None


def _safe_stderr(value: str) -> str:
    """Keep diagnostics useful without exposing RPC credentials or large output."""
    return sanitize_error(value)


def _resolve_cli_path(config: Config) -> str | None:
    """Resolve the configured CLI without relying on the caller's cwd."""
    configured = os.path.expanduser(config.cli_path)
    if os.path.sep in configured:
        return configured if os.path.isfile(configured) and os.access(configured, os.X_OK) else None
    # Keep bare names compatible with subprocess mocks and let subprocess
    # produce its normal diagnostic when PATH does not contain the program.
    return shutil.which(configured) or configured


def _format_version(value: Any, subversion: Any = None) -> str | None:
    """Format Ghost's numeric version while preserving unknown values."""
    if isinstance(value, int):
        major = value // 100_000_000
        minor = (value // 1_000_000) % 100
        patch = (value // 10_000) % 100
        build = value % 10_000
        return f"{major}.{minor}.{patch}.{build}"
    if isinstance(value, str) and value:
        return value
    if isinstance(subversion, str):
        match = re.search(r"(?:GhostCore|Ghost)[/:]?[vV]?([0-9]+(?:\.[0-9]+)+)", subversion)
        if match:
            return match.group(1)
    return None


def _build_command(method: str, config: Config, wallet: str | None = None, args: list[Any] | None = None) -> list[str] | None:
    """Build the exact argv passed to ghost-cli; no shell is involved."""
    cli_path = _resolve_cli_path(config)
    if cli_path is None:
        return None
    endpoint_args = []
    if config.rpc_host:
        endpoint_args.append(f"-rpcconnect={config.rpc_host}")
    if config.rpc_port is not None:
        endpoint_args.append(f"-rpcport={config.rpc_port}")
    return [cli_path, f"-datadir={os.path.expanduser(config.datadir)}", *endpoint_args,
            *([f"-rpcwallet={wallet}"] if wallet else []), method,
            *[_serialize_cli_arg(arg) for arg in (args or [])]]


def _call(method: str, config: Config, wallet: str | None = None, args: list[Any] | None = None) -> tuple[dict[str, Any] | list[Any] | str | None, str | None]:
    if method not in _ALLOWED_METHODS:
        return None, "RPC method is not allowed"
    argument_error = _validate_args(method, args)
    if argument_error:
        return None, argument_error
    command = _build_command(method, config, wallet, args)
    if command is None:
        LOG.warning("RPC method=%s failed: executable unavailable path=%s", method, config.cli_path)
        return None, "ghost-cli is unavailable"
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=config.timeout,
            check=False,
        )
    except (FileNotFoundError, PermissionError):
        LOG.warning("RPC method=%s failed: executable unavailable", method)
        return None, "ghost-cli is unavailable"
    except subprocess.TimeoutExpired:
        LOG.warning("RPC method=%s failed: timeout", method)
        return None, "RPC request timed out"
    except OSError:
        LOG.warning("RPC method=%s failed: OS error", method)
        return None, "Unable to execute ghost-cli"
    if completed.returncode != 0:
        detail = _safe_stderr(completed.stderr or "")
        LOG.warning("RPC method=%s failed: returncode=%s stderr=%s",
                    method, completed.returncode, detail or "<empty>")
        return None, "RPC request failed"
    raw_stdout = completed.stdout.strip()
    # Ghost Core returns empty stdout with exit code 0 for an absent UTXO.
    if method == "gettxout" and not raw_stdout:
        return None, None
    if method == "getblockhash" and re.fullmatch(r"[0-9a-fA-F]{64}", raw_stdout):
        return raw_stdout, None
    try:
        value = json.loads(completed.stdout)
    except (TypeError, ValueError):
        LOG.warning("RPC method=%s failed: invalid JSON stdout", method)
        return None, "RPC returned invalid JSON"
    if method == "gettxout" and value is None:
        return None, None
    if isinstance(value, str):
        if method == "getblockhash" and re.fullmatch(r"[0-9a-fA-F]{64}", value):
            return value, None
        return None, "RPC returned an invalid scalar response"
    if not isinstance(value, (dict, list)):
        return None, "RPC returned an unexpected response"
    return value, None


def collect_rpc(config: Config) -> Result:
    blockchain, blockchain_error = _call("getblockchaininfo", config)
    network, network_error = _call("getnetworkinfo", config)
    data: dict[str, Any] = {"blockchain": {}, "network": {}}
    if isinstance(blockchain, dict):
        data["blockchain"] = {
            "chain": blockchain.get("chain"),
            "blocks": blockchain.get("blocks"),
            "headers": blockchain.get("headers"),
            "verification_progress": blockchain.get("verificationprogress"),
            "initial_block_download": blockchain.get("initialblockdownload"),
        }
    if isinstance(network, dict):
        data["network"] = {
            "version": _format_version(network.get("version"), network.get("subversion")),
            "connections": network.get("connections"),
            "connections_in": network.get("connections_in"),
            "connections_out": network.get("connections_out"),
        }
    errors = [error for error in (blockchain_error, network_error) if error]
    if errors:
        status = Status.ERROR if blockchain is None and network is None else Status.WARN
        return Result(status, data, "; ".join(errors))
    required = ("chain", "blocks", "headers")
    if any(data["blockchain"].get(key) is None for key in required):
        return Result(Status.WARN, data, "RPC response is missing blockchain fields")
    return Result(Status.OK, data)
