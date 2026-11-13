from ghostnode.config import Config
from ghostnode.wallet_status import wallet_status_report


def config():
    return Config(cli_path="ghost-cli", datadir="/tmp/ghost", wallet_name="ghostmain")


def test_wallet_status_reports_staking_ready_without_sensitive_data():
    calls = []

    def rpc(method, cfg, wallet=None):
        calls.append((method, wallet))
        responses = {
            "listwallets": ["ghostmain"],
            "getwalletinfo": {"walletname": "ghostmain", "balance": 999},
            "getstakinginfo": {"enabled": True, "weight": 5},
        }
        return responses[method], None

    result = wallet_status_report(config(), rpc)
    assert result["status"] == "PASS"
    assert result["data"]["readiness"] == "WALLET_READY"
    assert result["data"]["staking_monitoring"] == "STAKING_MONITORING_READY"
    assert "balance" not in str(result)
    assert calls == [("listwallets", None), ("getwalletinfo", "ghostmain"),
                     ("getstakinginfo", "ghostmain")]


def test_wallet_status_distinguishes_node_only_mode_when_wallet_is_not_loaded():
    result = wallet_status_report(config(), lambda method, cfg, wallet=None: (["other"], None))
    assert result["status"] == "WARN"
    assert result["data"]["readiness"] == "WALLET_NOT_LOADED"
    assert result["data"]["node_monitoring"] == "NODE_ONLY_READY"


def test_wallet_status_does_not_infer_absence_from_rpc_error():
    result = wallet_status_report(config(), lambda method, cfg, wallet=None: (None, "wallet RPC unsupported"))
    assert result["status"] == "SKIP"
    assert result["data"]["readiness"] == "WALLET_STATUS_UNKNOWN"


def test_wallet_status_redacts_authentication_errors():
    result = wallet_status_report(config(), lambda method, cfg, wallet=None: (
        None, "rpcpassword=secret cookie=private"))
    assert "secret" not in str(result)
    assert "private" not in str(result)


def test_wallet_status_never_calls_mutating_methods():
    calls = []

    def rpc(method, cfg, wallet=None):
        calls.append(method)
        return (["ghostmain"], None) if method == "listwallets" else (
            {"walletname": "ghostmain"}, None) if method == "getwalletinfo" else (
            {"enabled": True}, None)

    wallet_status_report(config(), rpc)
    assert set(calls) <= {"listwallets", "getwalletinfo", "getstakinginfo"}
