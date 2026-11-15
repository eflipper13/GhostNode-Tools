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


def test_wallet_exposes_exact_additive_total_in_atomic_units(monkeypatch):
    balances = {"mine": {"trusted": 1000, "staked": 1003.18839195,
                          "blind_trusted": 0, "blind_untrusted_pending": 0,
                          "anon_trusted": 0, "anon_immature": 0,
                          "anon_untrusted_pending": 0, "untrusted_pending": 0,
                          "immature": 0}}
    def call(method, config, wallet=None):
        return ((["ghostmain"], None) if method == "listwallets"
                else ({"walletname": "ghostmain", "balance": 1000}, None)
                if method == "getwalletinfo" else (balances, None))
    monkeypatch.setattr(wallet, "_call", call)
    result = wallet.collect_wallet(Config())
    assert result.data["balances_atomic"]["trusted"] == 100000000000
    assert result.data["balances_atomic"]["staked"] == 100318839195
    assert result.data["total_balance_atomic"] == 200318839195


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
