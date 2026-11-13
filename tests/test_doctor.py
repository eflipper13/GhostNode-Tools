from pathlib import Path

from ghostnode.config import Config
from ghostnode.doctor import GhostCoreDoctor, report_dict
from ghostnode.setup_guidance import setup_report


def healthy_rpc(**overrides):
    responses = {
        "getblockchaininfo": {"chain": "main", "blocks": 10, "headers": 10,
                              "initialblockdownload": False},
        "getnetworkinfo": {"version": 23010000, "connections": 3},
        "getstakinginfo": {"enabled": True},
        "listwallets": ["ghostmain"],
        "getwalletinfo": {"walletname": "ghostmain", "unlocked_until": 0},
    }
    responses.update(overrides)
    return lambda method, config: (responses[method], None)


def local_config(tmp_path):
    cli = tmp_path / "ghost-cli"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o700)
    datadir = tmp_path / "ghost"
    datadir.mkdir()
    return Config(cli_path=str(cli), datadir=str(datadir))


def test_doctor_reports_healthy_local_node(tmp_path):
    checks = GhostCoreDoctor(local_config(tmp_path), rpc_call=healthy_rpc()).run()
    payload = report_dict(checks)
    assert payload["status"] == "PASS"
    assert {check["name"] for check in payload["checks"]} >= {
        "environment", "local_cli", "configuration", "rpc", "version",
        "network", "synchronization", "staking", "access",
    }


def test_doctor_handles_unreachable_rpc(tmp_path):
    def unavailable(method, config):
        return None, "RPC request timed out"

    payload = report_dict(GhostCoreDoctor(local_config(tmp_path), rpc_call=unavailable).run())
    assert payload["status"] == "FAIL"
    rpc = next(item for item in payload["checks"] if item["name"] == "rpc")
    assert rpc["status"] == "FAIL"
    assert "timed out" not in rpc["message"]


def test_doctor_does_not_expose_authentication_error(tmp_path):
    def auth_error(method, config):
        return None, "RPC request failed rpcpassword=secret cookie=private"

    payload = report_dict(GhostCoreDoctor(local_config(tmp_path), rpc_call=auth_error).run())
    rendered = str(payload)
    assert "secret" not in rendered
    assert "private" not in rendered
    assert "authentication" in next(item for item in payload["checks"]
                                    if item["name"] == "rpc")["message"]


def test_doctor_allows_remote_rpc_when_local_cli_is_missing(tmp_path):
    config = Config(cli_path=str(tmp_path / "missing-ghost-cli"),
                    datadir=str(tmp_path / "missing-data"),
                    rpc_host="node.example", rpc_port=51725)
    checks = GhostCoreDoctor(config, rpc_call=healthy_rpc()).run()
    local_cli = next(check for check in checks if check.name == "local_cli")
    assert local_cli.status == "SKIP"
    assert next(check for check in checks if check.name == "rpc").status == "PASS"


def test_doctor_reports_wallet_not_loaded_as_node_only_ready(tmp_path):
    rpc = healthy_rpc(listwallets=["other"])
    checks = GhostCoreDoctor(local_config(tmp_path), rpc_call=rpc).run()
    wallet = next(check for check in checks if check.name == "wallet")
    assert wallet.status == "WARN"
    assert wallet.details["readiness"] == "WALLET_NOT_LOADED"
    assert wallet.details["node_monitoring"] == "NODE_ONLY_READY"


def test_doctor_reports_wallet_and_staking_readiness(tmp_path):
    checks = GhostCoreDoctor(local_config(tmp_path), rpc_call=healthy_rpc()).run()
    wallet = next(check for check in checks if check.name == "wallet")
    assert wallet.status == "PASS"
    assert wallet.details["readiness"] == "WALLET_READY"
    assert wallet.details["staking_monitoring"] == "STAKING_MONITORING_READY"


def test_doctor_warns_for_unknown_version_and_unsynchronized_chain(tmp_path):
    rpc = healthy_rpc(getnetworkinfo={"subversion": "/GhostCore:9.9.9/"},
                      getblockchaininfo={"chain": "main", "blocks": 8, "headers": 10,
                                         "initialblockdownload": True})
    checks = GhostCoreDoctor(local_config(tmp_path), rpc_call=rpc).run()
    assert next(check for check in checks if check.name == "version").status == "WARN"
    assert next(check for check in checks if check.name == "synchronization").status == "WARN"
    assert report_dict(checks)["status"] == "WARN"


def test_doctor_rejects_wrong_network(tmp_path):
    rpc = healthy_rpc(getblockchaininfo={"chain": "test", "blocks": 1, "headers": 1,
                                         "initialblockdownload": False})
    checks = GhostCoreDoctor(local_config(tmp_path), rpc_call=rpc).run()
    assert next(check for check in checks if check.name == "network").status == "FAIL"


def test_doctor_repeated_runs_are_read_only(tmp_path):
    calls = []

    def rpc(method, config):
        calls.append(method)
        return healthy_rpc()(method, config)

    doctor = GhostCoreDoctor(local_config(tmp_path), rpc_call=rpc)
    first = report_dict(doctor.run())
    second = report_dict(doctor.run())
    assert first == second
    assert calls == ["getblockchaininfo", "getnetworkinfo", "getstakinginfo",
                     "listwallets", "getwalletinfo", "getstakinginfo",
                     "listwallets", "getwalletinfo", "getstakinginfo"]
    assert not list((Path(tmp_path) / "ghost").iterdir())


def test_setup_is_dry_run_and_reports_unverified_sources(tmp_path, monkeypatch):
    monkeypatch.setattr("ghostnode.setup_guidance.platform.system", lambda: "Windows")
    monkeypatch.setattr("ghostnode.setup_guidance.platform.machine", lambda: "AMD64")
    payload = setup_report(Config(cli_path=str(tmp_path / "missing"), datadir=str(tmp_path / "data")))
    assert payload["environment"] == {"system": "Windows", "architecture": "AMD64",
                                      "python": payload["environment"]["python"]}
    assert payload["status"] == "WARN"
    assert any("not verified" in limitation.lower() for limitation in payload["limitations"])
