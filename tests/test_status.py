import json
import subprocess

from click.testing import CliRunner

from ghostnode.cli import cli
from ghostnode.collectors import rpc, service
from ghostnode.commands import status as status_command
from ghostnode.config import Config


def completed(stdout, returncode=0):
    return subprocess.CompletedProcess(["ghost-cli"], returncode, stdout, "secret-like error")


def test_rpc_success(monkeypatch):
    responses = [
        '{"chain": "main", "blocks": 10, "headers": 11, "verificationprogress": 0.9, "initialblockdownload": false}',
        '{"version": 23010000, "subversion": "/GhostCore:0.23.1.0/", "connections": 8, "connections_in": 3, "connections_out": 5}',
    ]
    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: completed(responses.pop(0)))
    result = rpc.collect_rpc(Config(cli_path="fake", datadir="/tmp/safe"))
    assert result.status.value == "OK"
    assert result.data["blockchain"]["chain"] == "main"
    assert result.data["blockchain"]["initial_block_download"] is False
    assert result.data["network"]["version"] == "0.23.1.0"
    assert result.data["network"]["connections_in"] == 3


def test_version_uses_subversion_when_numeric_version_missing(monkeypatch):
    responses = ['{"chain":"main", "blocks":1, "headers":1, "initialblockdownload":true}', '{"subversion":"/GhostCore:0.23.1.0/"}']
    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: completed(responses.pop(0)))
    result = rpc.collect_rpc(Config(cli_path="fake"))
    assert result.data["network"]["version"] == "0.23.1.0"
    assert result.data["blockchain"]["initial_block_download"] is True


def test_status_text_flattens_nested_fields(monkeypatch):
    monkeypatch.setattr(status_command, "collect_rpc", lambda config: rpc.Result(rpc.Status.OK, {"blockchain": {"blocks": 3}, "network": {"version": "0.23.1.0"}}))
    monkeypatch.setattr(status_command, "collect_service", lambda config: service.Result(service.Status.OK, {"activeState": "active", "subState": "running"}))
    result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "Rpc Data Blockchain Blocks: 3" in result.output
    assert "Rpc Data Network Version: 0.23.1.0" in result.output
    assert "{" not in result.output


def test_rpc_timeout_and_invalid_json(monkeypatch):
    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("x", 5)))
    result = rpc.collect_rpc(Config(cli_path="fake"))
    assert result.status.value == "ERROR"
    assert "timed out" in result.message

    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: completed("not-json"))
    result = rpc.collect_rpc(Config(cli_path="fake"))
    assert result.status.value == "ERROR"
    assert "invalid JSON" in result.message


def test_rpc_missing_fields_is_warn(monkeypatch):
    responses = ['{"chain":"main"}', '{}']
    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: completed(responses.pop(0)))
    assert rpc.collect_rpc(Config(cli_path="fake")).status.value == "WARN"


def test_service_states_and_unavailable(monkeypatch):
    monkeypatch.setattr(service.subprocess, "run", lambda *args, **kwargs: completed("ActiveState=active\nSubState=running\n"))
    assert service.collect_service(Config()).status.value == "OK"
    monkeypatch.setattr(service.subprocess, "run", lambda *args, **kwargs: completed("ActiveState=inactive\nSubState=dead\n"))
    assert service.collect_service(Config()).status.value == "WARN"
    monkeypatch.setattr(service.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError()))
    assert service.collect_service(Config()).status.value == "UNKNOWN"


def test_status_json_keeps_partial_results(monkeypatch):
    monkeypatch.setattr(rpc, "collect_rpc", lambda config: rpc.Result(rpc.Status.ERROR, {"blockchain": {}, "network": {}}, "RPC request failed"))
    monkeypatch.setattr(service, "collect_service", lambda config: service.Result(service.Status.UNKNOWN, {}, "systemd is unavailable"))
    result = CliRunner().invoke(cli, ["status", "--json"])
    payload = json.loads(result.output)
    assert result.exit_code == 1
    assert payload["status"] == "ERROR"
    assert set(payload["data"]) == {"rpc", "service"}
    assert "secret-like" not in result.output
