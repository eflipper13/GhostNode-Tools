import json
from pathlib import Path

from ghostnode.intelligence.reward_adapter import EvidenceStatus, OwnershipStatus, normalize_reward_transaction


FIXTURE = json.loads((Path(__file__).parent / "fixtures/ghost_pos_block_1658759.json").read_text())
PREV_TX = "d" * 64
PREV_BLOCK = "e" * 64


def test_fixture_normalization_is_conservative_without_wallet_proof():
    calls = []

    def rpc(method, args):
        calls.append((method, args))
        if method == "gettxout":
            return None, None
        if method == "getrawtransaction":
            return ({"txid": args[0], "blockhash": PREV_BLOCK,
                     "vout": [{"value": 1500, "scriptPubKey": {"addresses": ["external"]}}]}, None)
        if method == "getaddressinfo":
            return ({"ismine": False, "solvable": True}, None)
        raise AssertionError(method)

    result = normalize_reward_transaction(FIXTURE, rpc,
                                          {FIXTURE["tx"][0]["vin"][0]["txid"]: PREV_BLOCK})
    assert len(result.txid) == 64
    assert result.status is EvidenceStatus.PARTIAL
    assert all(output.ownership_status is not OwnershipStatus.CONFIRMED for output in result.outputs)
    assert result.attribution.wallet_reward_atomic is None
    assert {method for method, _ in calls} == {"gettxout", "getrawtransaction", "getaddressinfo"}


def test_verified_outputs_require_explicit_wallet_rpc_proof():
    block = {"hash": "b", "height": 10, "tx": [{
        "txid": "t", "vin": [{"txid": PREV_TX, "vout": 0}],
        "vout": [
            {"n": 0, "value": 10, "output_class": "principal", "scriptPubKey": {"addresses": ["mine"]}},
            {"n": 1, "value": 1, "output_class": "wallet_reward", "scriptPubKey": {"addresses": ["mine"]}},
        ],
    }]}

    def rpc(method, args):
        if method == "gettxout":
            return None, None
        if method == "getrawtransaction":
            return ({"txid": PREV_TX, "blockhash": PREV_BLOCK,
                     "vout": [{"value": 10, "scriptPubKey": {"addresses": ["mine"]}}]}, None)
        if method == "getaddressinfo":
            return ({"ismine": True, "solvable": True}, None)
        raise AssertionError(method)

    result = normalize_reward_transaction(block, rpc, {PREV_TX: PREV_BLOCK})
    assert result.status is EvidenceStatus.VERIFIED
    assert result.attribution.wallet_reward_atomic == 1 * 100_000_000


def test_missing_prevout_and_bad_vout_remain_unknown():
    block = {"tx": [{"txid": "t", "vin": [{"txid": "missing", "vout": 9}], "vout": []}]}

    def rpc(method, args):
        return None, "NOT_FOUND"

    result = normalize_reward_transaction(block, rpc)
    assert result.status is EvidenceStatus.PARTIAL
    assert result.inputs[0].value_atomic is None
    assert result.inputs[0].ownership_status is OwnershipStatus.UNKNOWN
    assert result.attribution.wallet_reward_atomic is None


def test_current_utxo_prevout_is_normalized_from_gettxout():
    block = {"tx": [{"txid": "t", "vin": [{"txid": PREV_TX, "vout": 0}],
                     "vout": [{"n": 0, "value": 1, "output_class": "principal",
                                "scriptPubKey": {"addresses": ["mine"]}}]}]}

    def rpc(method, args):
        if method == "gettxout":
            return {"value": 10, "scriptPubKey": {"addresses": ["mine"]}}, None
        if method == "getaddressinfo":
            return {"ismine": True}, None
        raise AssertionError(method)

    result = normalize_reward_transaction(block, rpc)
    assert result.inputs[0].value_atomic == 1_000_000_000
    assert result.inputs[0].ownership_status is OwnershipStatus.CONFIRMED


def test_txid_mismatch_is_not_accepted():
    block = {"tx": [{"txid": "t", "vin": [{"txid": "p", "vout": 0}], "vout": []}]}

    def rpc(method, args):
        return ({"txid": "other", "vout": []}, None)

    result = normalize_reward_transaction(block, rpc)
    assert result.inputs[0].confidence is EvidenceStatus.UNKNOWN
