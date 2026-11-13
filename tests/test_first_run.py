from pathlib import Path

from ghostnode.config import Config
from ghostnode.first_run import first_run_report


def local_config(tmp_path, wallet_name="ghostmain"):
    cli = tmp_path / "ghost-cli"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o700)
    datadir = tmp_path / "ghost"
    datadir.mkdir()
    return Config(cli_path=str(cli), datadir=str(datadir), wallet_name=wallet_name)


def rpc_responses(**overrides):
    responses = {
        "getblockchaininfo": {"chain": "main", "blocks": 10, "headers": 10,
                              "initialblockdownload": False},
        "getnetworkinfo": {"version": 23010000},
        "getstakinginfo": {"enabled": True, "staking": True},
        "listwallets": ["ghostmain"],
        "getwalletinfo": {"walletname": "ghostmain"},
    }
    responses.update(overrides)
    return responses


def test_init_healthy_local_wallet_is_repeatable_and_read_only(tmp_path):
    calls = []
    responses = rpc_responses()

    def rpc(method, config):
        calls.append(method)
        return responses[method], None

    config = local_config(tmp_path)
    before = sorted(Path(config.datadir).iterdir())
    first = first_run_report(config, rpc_call=rpc)
    second = first_run_report(config, rpc_call=rpc)

    assert first["status"] == "WARN"  # backup verification is intentionally unverified
    assert first["mode"] == "LOCAL_WALLET"
    assert first == second
    assert first["security"]["filesystem_written"] is False
    assert first["security"]["backup_status"] == "GUIDANCE_AVAILABLE"
    assert sorted(Path(config.datadir).iterdir()) == before
    assert "wallet-changing" not in str(first).lower()
    assert set(calls) <= {"getblockchaininfo", "getnetworkinfo", "getstakinginfo",
                          "listwallets", "getwalletinfo"}


def test_init_without_wallet_supports_node_only_mode(tmp_path):
    responses = rpc_responses(listwallets=[])
    report = first_run_report(local_config(tmp_path), rpc_call=lambda method, config: (responses[method], None))
    assert report["mode"] == "NODE_ONLY"
    wallet_stage = next(stage for stage in report["stages"] if stage["name"] == "wallet")
    assert wallet_stage["status"] == "WARN"
    assert "NODE_ONLY" in " ".join(report["next_steps"])


def test_init_remote_node_does_not_require_local_cli(tmp_path):
    config = Config(cli_path=str(tmp_path / "missing-cli"), datadir=str(tmp_path / "missing-data"),
                    rpc_host="node.example", rpc_port=51725)
    responses = rpc_responses(listwallets=[])
    report = first_run_report(config, rpc_call=lambda method, config: (responses[method], None))
    assert report["mode"] == "REMOTE_NODE"
    environment = next(stage for stage in report["stages"] if stage["name"] == "environment")
    assert any(check["name"] == "local_cli" and check["status"] == "SKIP"
               for check in environment["checks"])
    location = next(stage for stage in report["stages"] if stage["name"] == "wallet_security")["details"]["wallet_location"]
    assert location["scope"] == "remote"
    assert location["path"] is None


def test_init_missing_rpc_is_fail_without_secret_leak(tmp_path):
    def unavailable(method, config):
        return None, "RPC authentication failed rpcpassword=secret cookie=private"

    report = first_run_report(local_config(tmp_path), rpc_call=unavailable)
    assert report["status"] == "FAIL"
    assert "secret" not in str(report)
    assert "private" not in str(report)


def test_init_unsynchronized_node_warns_and_unknown_wallet_path_is_explicit(tmp_path):
    responses = rpc_responses(getblockchaininfo={"chain": "main", "blocks": 8,
                                                  "headers": 10, "initialblockdownload": True},
                              listwallets=[])
    report = first_run_report(local_config(tmp_path), rpc_call=lambda method, config: (responses[method], None))
    assert report["status"] == "WARN"
    sync = next(stage for stage in report["stages"] if stage["name"] == "rpc")
    assert any(check["name"] == "synchronization" for stage in report["stages"]
               if stage["name"] == "staking" for check in stage["checks"])
    security = next(stage for stage in report["stages"] if stage["name"] == "wallet_security")
    assert security["details"]["backup_status"] == "GUIDANCE_AVAILABLE"
    assert security["details"]["wallet_location"]["status"] == "WALLET_PATH_UNKNOWN"
