import json
import pytest

from ghostnode.collectors import rpc
from ghostnode.config import Config


def test_explicit_executable_path_is_passed_to_rpc_client(tmp_path, monkeypatch):
    cli = tmp_path / "ghost-cli"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o700)
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return type("Completed", (), {"returncode": 0, "stdout": json.dumps({"blocks": 1}), "stderr": ""})()

    monkeypatch.setattr(rpc.subprocess, "run", fake_run)
    value, error = rpc._call("getblockchaininfo", Config(cli_path=str(cli), datadir=str(tmp_path)))
    assert error is None
    assert value == {"blocks": 1}
    assert seen["args"][0] == str(cli)


def test_nonexistent_executable_is_reported_without_subprocess(tmp_path, monkeypatch):
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr(rpc.subprocess, "run", fake_run)
    value, error = rpc._call("getblockchaininfo", Config(cli_path=str(tmp_path / "missing")))
    assert value is None
    assert error == "ghost-cli is unavailable"
    assert called is False


def test_bare_cli_name_uses_path_lookup(monkeypatch):
    monkeypatch.setattr(rpc.shutil, "which", lambda name: "/isolated/ghost-cli" if name == "ghost-cli" else None)
    assert rpc._resolve_cli_path(Config(cli_path="ghost-cli")) == "/isolated/ghost-cli"


def test_missing_bare_cli_name_is_left_for_subprocess(monkeypatch):
    monkeypatch.setattr(rpc.shutil, "which", lambda name: None)
    assert rpc._resolve_cli_path(Config(cli_path="ghost-cli")) == "ghost-cli"


def test_preflight_uses_mocked_read_only_rpc(tmp_path, monkeypatch):
    from ghostnode.intelligence.runner import CollectorRunner

    runner = CollectorRunner(Config(cli_path="ghost-cli", datadir=str(tmp_path)), tmp_path / "db.sqlite3")
    calls = []

    def fake_call(method, config, wallet=None):
        calls.append((method, wallet))
        return ({"ok": True}, None)

    monkeypatch.setattr("ghostnode.intelligence.runner._call", fake_call)
    assert runner.preflight() == (True, None)
    assert calls == [("getblockchaininfo", None), ("getstakinginfo", None)]


def test_command_matches_runner_environment_without_wallet_for_node_probe(tmp_path):
    cli = tmp_path / "ghost-cli"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o700)
    config = Config(cli_path=str(cli), datadir="/tmp/ghost-data")
    assert rpc._build_command("getblockchaininfo", config) == [
        str(cli), "-datadir=/tmp/ghost-data", "getblockchaininfo"
    ]
    assert rpc._build_command("getstakinginfo", config) == [
        str(cli), "-datadir=/tmp/ghost-data", "getstakinginfo"
    ]


def test_wallet_context_is_only_added_when_explicitly_requested(tmp_path):
    cli = tmp_path / "ghost-cli"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o700)
    config = Config(cli_path=str(cli), datadir=str(tmp_path))
    assert "-rpcwallet=ghostmain" not in rpc._build_command("getstakinginfo", config)
    assert "-rpcwallet=ghostmain" in rpc._build_command("getbalances", config, wallet="ghostmain")


def test_rpc_arguments_are_forwarded_after_method(tmp_path):
    cli = tmp_path / "ghost-cli"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o700)
    config = Config(cli_path=str(cli), datadir=str(tmp_path))
    assert rpc._build_command("getblock", config, args=["hash", 2, True])[-4:] == ["getblock", "hash", "2", "true"]


@pytest.mark.parametrize("value,expected", [(True, "true"), (False, "false"), (None, "null"),
                                              (7, "7"), (1.5, "1.5"), ("hash", "hash")])
def test_typed_cli_argument_serialization(value, expected):
    assert rpc._serialize_cli_arg(value) == expected


def test_getblock_command_serializes_boolean_as_json(tmp_path):
    cli = tmp_path / "ghost-cli"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o700)
    command = rpc._build_command("getblock", Config(cli_path=str(cli), datadir=str(tmp_path)),
                                 args=["a" * 64, 2, True])
    assert command[-3:] == ["a" * 64, "2", "true"]


def test_unsupported_cli_argument_type_is_rejected(tmp_path):
    cli = tmp_path / "ghost-cli"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o700)
    with pytest.raises(TypeError):
        rpc._build_command("getblock", Config(cli_path=str(cli), datadir=str(tmp_path)), args=[object()])


def test_rpc_mutating_methods_are_rejected(tmp_path, monkeypatch):
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(rpc.subprocess, "run", fake_run)
    value, error = rpc._call("sendtoaddress", Config(cli_path=str(tmp_path / "ghost-cli")))
    assert value is None
    assert error == "RPC method is not allowed"
    assert called is False


@pytest.mark.parametrize("method,args", [
    ("getblockhash", []), ("getblockhash", [True]), ("getblockreward", [-1]),
    ("getblock", []), ("getblock", ["h", 3]),
    ("listtransactions", ["*", 1001, 0]), ("listunspent", [5, 1]),
])
def test_invalid_rpc_arguments_do_not_start_subprocess(tmp_path, monkeypatch, method, args):
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(rpc.subprocess, "run", fake_run)
    value, error = rpc._call(method, Config(cli_path="ghost-cli"), args=args)
    assert value is None
    assert error
    assert called is False


def test_no_argument_methods_reject_extra_arguments(tmp_path, monkeypatch):
    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    value, error = rpc._call("getnetworkinfo", Config(cli_path="ghost-cli"), args=["unexpected"])
    assert value is None
    assert error == "RPC method does not accept arguments"


def test_getblockhash_accepts_valid_scalar_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: type("C", (), {
        "returncode": 0, "stdout": '"' + "a" * 64 + '"', "stderr": ""
    })())
    value, error = rpc._call("getblockhash", Config(cli_path="ghost-cli"), args=[1])
    assert value == "a" * 64
    assert error is None


@pytest.mark.parametrize("stdout", ["a" * 64, "a" * 64 + "\n", "  A" * 0 + "A" * 64 + " \n"])
def test_getblockhash_accepts_raw_hash_with_outer_whitespace(monkeypatch, stdout):
    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: type("C", (), {
        "returncode": 0, "stdout": stdout, "stderr": ""
    })())
    value, error = rpc._call("getblockhash", Config(cli_path="ghost-cli"), args=[1])
    assert value == stdout.strip()
    assert error is None


@pytest.mark.parametrize("stdout", ["x" * 63, "x" * 65, "prefix-" + "a" * 64, "a" * 64 + "-suffix"])
def test_getblockhash_rejects_raw_invalid_hash(monkeypatch, stdout):
    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: type("C", (), {
        "returncode": 0, "stdout": stdout, "stderr": ""
    })())
    value, error = rpc._call("getblockhash", Config(cli_path="ghost-cli"), args=[1])
    assert value is None
    assert error


@pytest.mark.parametrize("payload", ['"short"', '"' + "g" * 64 + '"', '123', 'true', 'null'])
def test_getblockhash_rejects_invalid_scalar_or_type(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: type("C", (), {
        "returncode": 0, "stdout": payload, "stderr": ""
    })())
    value, error = rpc._call("getblockhash", Config(cli_path="ghost-cli"), args=[1])
    assert value is None
    assert error


def test_dict_and_list_responses_remain_supported(monkeypatch):
    responses = ['{"blocks": 1}', '[{"id": 1}]']
    def fake_run(*args, **kwargs):
        return type("C", (), {"returncode": 0, "stdout": responses.pop(0), "stderr": ""})()
    monkeypatch.setattr(rpc.subprocess, "run", fake_run)
    value, error = rpc._call("getblockchaininfo", Config(cli_path="ghost-cli"))
    assert value == {"blocks": 1} and error is None
    value, error = rpc._call("getpeerinfo", Config(cli_path="ghost-cli"))
    assert value == [{"id": 1}] and error is None


def test_gettxout_empty_stdout_means_absent_utxo(monkeypatch):
    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: type("C", (), {
        "returncode": 0, "stdout": "", "stderr": ""
    })())

    value, error = rpc._call(
        "gettxout", Config(cli_path="ghost-cli"),
        args=["a" * 64, 23, True]
    )

    assert value is None
    assert error is None


def test_listunspent_is_read_only_and_accepts_valid_arguments(monkeypatch):
    monkeypatch.setattr(rpc.subprocess, "run", lambda *args, **kwargs: type("C", (), {
        "returncode": 0, "stdout": "[]", "stderr": ""
    })())
    value, error = rpc._call("listunspent", Config(cli_path="ghost-cli"),
                             wallet="ghostmain", args=[0, 9999999])
    assert value == [] and error is None


def test_listunspent_rejects_invalid_arguments_without_subprocess(monkeypatch):
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(rpc.subprocess, "run", fake_run)
    value, error = rpc._call("listunspent", Config(cli_path="ghost-cli"), args=[0, "many"])
    assert value is None and error and called is False


def test_rpc_stderr_is_sanitized_without_losing_error_context():
    txid = "a" * 64
    address = "G" + "A" * 30
    raw = f"RPC error txid={txid} address={address} rpcpassword=secret wallet=/tmp/node/.ghost/wallet.dat"
    safe = rpc._safe_stderr(raw)
    assert txid not in safe
    assert address not in safe
    assert "secret" not in safe
    assert "[REDACTED" in safe
    assert "RPC error" in safe
