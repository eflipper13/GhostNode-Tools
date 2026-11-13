from ghostnode.intelligence.wallet_history import build_verified_history_index


TX = "a" * 64
BLOCK = "b" * 64


def test_history_index_requires_height_and_independent_hash_verification():
    calls = []

    def rpc(method, args):
        calls.append((method, args))
        return BLOCK, None

    entries = [{"txid": TX, "blockhash": BLOCK, "blockheight": 42}]
    assert build_verified_history_index(entries, rpc) == {TX: BLOCK}
    assert calls == [("getblockhash", [42])]


def test_history_index_rejects_mismatch_and_conflicts_deterministically():
    other = "c" * 64

    def rpc(method, args):
        return (BLOCK if args[0] == 1 else other), None

    entries = [
        {"txid": TX, "blockhash": BLOCK, "blockheight": 1},
        {"txid": TX, "blockhash": other, "blockheight": 2},
    ]
    assert build_verified_history_index(entries, rpc) == {}


def test_history_index_caches_blockhashes_and_ignores_incomplete_history():
    calls = []

    def rpc(method, args):
        calls.append(args[0])
        return BLOCK, None

    entries = [
        {"txid": TX, "blockhash": BLOCK, "blockheight": 5},
        {"txid": "d" * 64, "blockhash": BLOCK, "blockheight": 5},
        {"txid": "bad", "blockhash": BLOCK, "blockheight": 5},
    ]
    assert len(build_verified_history_index(entries, rpc)) == 2
    assert calls == [5]
