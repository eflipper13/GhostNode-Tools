from ghostnode.collectors import wallet
from ghostnode.config import Config


def test_loaded_wallet_read_only(monkeypatch):
    calls = []
    def call(method, config, wallet=None):
        calls.append((method, wallet))
        return ((["ghostmain"], None) if method == "listwallets" else ({"walletname": "ghostmain", "balance": 12.5, "unlocked_until": 0}, None) if method == "getwalletinfo" else ({"mine": {"trusted": 12.5}}, None))
    monkeypatch.setattr(wallet, "_call", call)
    result = wallet.collect_wallet(Config())
    assert result.status.value == "OK"
    assert result.data["balance"] == 12.5
    assert result.data["encryption"] == "locked"
    assert calls == [("listwallets", None), ("getwalletinfo", "ghostmain"), ("getbalances", "ghostmain")]


def test_wallet_not_loaded_is_not_zero(monkeypatch):
    monkeypatch.setattr(wallet, "_call", lambda method, config, wallet=None: (["other"], None))
    result = wallet.collect_wallet(Config())
    assert result.status.value == "WARN"
    assert result.data["balance"] is None
    assert "NOT LOADED" in result.message


def test_wallet_rpc_unavailable(monkeypatch):
    monkeypatch.setattr(wallet, "_call", lambda method, config, wallet=None: (None, "RPC request failed"))
    result = wallet.collect_wallet(Config())
    assert result.status.value == "UNKNOWN"
    assert result.data["balance"] is None
