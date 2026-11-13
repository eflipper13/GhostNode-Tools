from ghostnode.intelligence.prevout_resolver import PrevoutResolver, PrevoutStatus


TXID = "a" * 64
BLOCK = "b" * 64


def fake_rpc(responses):
    calls = []

    def rpc(method, args):
        calls.append((method, args))
        return responses.get(method, (None, "unavailable"))

    rpc.calls = calls
    return rpc


def test_current_utxo_is_first_source():
    rpc = fake_rpc({"gettxout": ({"value": 1.25, "bestblock": BLOCK}, None)})
    result = PrevoutResolver(rpc).resolve(TXID, 2)
    assert result.status is PrevoutStatus.VERIFIED
    assert result.value == 1.25
    assert [name for name, _ in rpc.calls] == ["gettxout"]


def test_spent_output_uses_verified_index_and_blockhash():
    transaction = {"txid": TXID, "blockhash": BLOCK,
                   "vout": [{"value": 3.5}]}
    rpc = fake_rpc({"gettxout": (None, None), "getrawtransaction": (transaction, None)})
    result = PrevoutResolver(rpc).resolve(TXID, 0, {TXID: BLOCK})
    assert result.status is PrevoutStatus.VERIFIED
    assert result.value == 3.5
    assert rpc.calls[-1] == ("getrawtransaction", [TXID, 1, BLOCK])


def test_no_blockhash_does_not_guess_history():
    rpc = fake_rpc({"gettxout": (None, "spent")})
    result = PrevoutResolver(rpc).resolve(TXID, 0)
    assert result.status is PrevoutStatus.UNKNOWN
    assert [name for name, _ in rpc.calls] == ["gettxout"]


def test_invalid_inputs_and_duplicate_prevout():
    rpc = fake_rpc({"gettxout": (None, "spent")})
    resolver = PrevoutResolver(rpc)
    assert resolver.resolve("bad", 0).status is PrevoutStatus.INVALID
    assert resolver.resolve(TXID, -1).status is PrevoutStatus.INVALID
    results = resolver.resolve_many([(TXID, 0), (TXID, 0)])
    assert [r.status for r in results] == [PrevoutStatus.UNKNOWN, PrevoutStatus.INVALID]


def test_historical_validation_rejects_mismatch_and_bad_values():
    bad_tx = {"txid": "c" * 64, "blockhash": BLOCK, "vout": [{"value": 1}]}
    rpc = fake_rpc({"gettxout": (None, "spent"), "getrawtransaction": (bad_tx, None)})
    assert PrevoutResolver(rpc).resolve(TXID, 0, {TXID: BLOCK}).status is PrevoutStatus.INVALID

    bad_value = {"txid": TXID, "blockhash": BLOCK, "vout": [{"value": -1}]}
    rpc = fake_rpc({"gettxout": (None, "spent"), "getrawtransaction": (bad_value, None)})
    assert PrevoutResolver(rpc).resolve(TXID, 0, {TXID: BLOCK}).status is PrevoutStatus.INVALID


def test_missing_vout_empty_response_and_rpc_error_are_conservative():
    for transaction, error in (({"txid": TXID, "blockhash": BLOCK, "vout": []}, None),
                               (None, "RPC error")):
        rpc = fake_rpc({"gettxout": (None, "spent"),
                        "getrawtransaction": (transaction, error)})
        result = PrevoutResolver(rpc).resolve(TXID, 0, {TXID: BLOCK})
        assert result.status is PrevoutStatus.INVALID if error is None else PrevoutStatus.UNKNOWN
