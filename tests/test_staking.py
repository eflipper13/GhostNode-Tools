from ghostnode.collectors import staking
from ghostnode.config import Config
import math


def test_active_staking(monkeypatch):
    responses = {
        "getposdifficulty": ({"netstakeweight": 900, "difficulty": 4.5}, None),
        "getstakinginfo": ({"enabled": True, "staking": True, "weight": 100, "netstakeweight": 900, "expectedtime": 3600, "difficulty": 4.5, "percentyearreward": 12.0}, None),
    }
    monkeypatch.setattr(staking, "_call", lambda method, config, wallet=None: responses[method])
    result = staking.collect_staking(Config(), loaded=True)
    assert result.status.value == "OK"
    assert result.data["wallet_weight"] == 100
    assert result.data["expected_time"] == 3600
    assert result.data["intelligence"]["wallet_share_percent"] == 11.111111
    assert 0 < result.data["intelligence"]["probability_24h_percent"] <= 100
    assert result.data["intelligence"]["historical_data_available"] is False


def test_locked_wallet_cause(monkeypatch):
    monkeypatch.setattr(staking, "_call", lambda method, config, wallet=None: (({"netstakeweight": 1, "difficulty": 1}, None) if method == "getposdifficulty" else ({"enabled": True, "staking": False, "cause": "locked"}, None)))
    result = staking.collect_staking(Config(), loaded=True)
    assert result.status.value == "WARN"
    assert result.data["cause_description"] == "Wallet is locked"


def test_not_loaded_does_not_call_wallet_staking_rpc(monkeypatch):
    calls = []
    def call(method, config, wallet=None):
        calls.append(method)
        return ({"netstakeweight": 1, "difficulty": 1}, None)
    monkeypatch.setattr(staking, "_call", call)
    result = staking.collect_staking(Config(), loaded=False)
    assert result.status.value == "WARN"
    assert calls == ["getposdifficulty"]


def test_staking_rpc_error(monkeypatch):
    monkeypatch.setattr(staking, "_call", lambda method, config, wallet=None: (None, "RPC request failed"))
    assert staking.collect_staking(Config(), loaded=True).status.value == "UNKNOWN"


def test_expected_time_is_not_presented_as_guarantee(monkeypatch):
    responses = {
        "getposdifficulty": ({"netstakeweight": 1000, "difficulty": 2}, None),
        "getstakinginfo": ({"enabled": True, "staking": True, "weight": 10, "expectedtime": 86400}, None),
    }
    monkeypatch.setattr(staking, "_call", lambda method, config, wallet=None: responses[method])
    result = staking.collect_staking(Config(), loaded=True)
    assert result.data["intelligence"]["probability_24h_percent"] == 63.21
    assert result.data["intelligence"]["history_note"]


def test_invalid_numeric_inputs_do_not_create_predictions(monkeypatch):
    invalid_values = [True, float("nan"), float("inf"), float("-inf"), -1, 0, "86400", None]
    for expected_time in invalid_values:
        responses = {
            "getposdifficulty": ({"netstakeweight": 1000, "difficulty": 2}, None),
            "getstakinginfo": ({"enabled": True, "staking": True, "weight": 10, "expectedtime": expected_time}, None),
        }
        monkeypatch.setattr(staking, "_call", lambda method, config, wallet=None: responses[method])
        result = staking.collect_staking(Config(), loaded=True)
        assert result.data["expected_time"] is None
        assert result.data["intelligence"]["probability_24h_percent"] is None


def test_invalid_weights_are_not_used_for_share(monkeypatch):
    responses = {
        "getposdifficulty": ({"netstakeweight": True, "difficulty": math.inf}, None),
        "getstakinginfo": ({"enabled": True, "staking": True, "weight": -5, "expectedtime": 10**30}, None),
    }
    monkeypatch.setattr(staking, "_call", lambda method, config, wallet=None: responses[method])
    result = staking.collect_staking(Config(), loaded=True)
    assert result.data["network_weight"] is None
    assert result.data["wallet_weight"] is None
    assert result.data["intelligence"]["wallet_share_percent"] is None
    assert result.data["intelligence"]["probability_30d_percent"] == 0.0


def test_probability_windows_follow_poisson_model():
    expected = 86400
    assert staking._probability(expected, 86400) == 63.21
    assert staking._probability(expected, 604800) == 99.91
    assert staking._probability(expected, 2592000) == 100.0
