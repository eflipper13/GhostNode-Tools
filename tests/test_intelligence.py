import sqlite3
import multiprocessing
import os
import signal
import time
import json
from pathlib import Path

from ghostnode.intelligence.collectors import collect_snapshot, scan_block, is_pos_transaction
from ghostnode.intelligence.db import IntelligenceDB
from ghostnode.intelligence.lock import CollectorLock


def test_real_pos_fixture_1658759_structure_and_detection():
    fixture = json.loads((Path(__file__).parent / "fixtures/ghost_pos_block_1658759.json").read_text())
    assert fixture["height"] == 1658759
    assert len(fixture["hash"]) == 64
    assert fixture["nTx"] == 1
    assert len(fixture["tx"]) == 1
    transaction = fixture["tx"][0]
    assert len(transaction["txid"]) == 64
    assert len(transaction["vin"]) == 1
    assert len(transaction["vout"]) == 4
    assert transaction["vout"][0]["type"] == "data"
    assert "OP_ISCOINSTAKE" in transaction["vout"][1]["scriptPubKey"]["asm"]
    assert "OP_ISCOINSTAKE" in transaction["vout"][2]["scriptPubKey"]["asm"]
    assert "OP_ISCOINSTAKE" not in transaction["vout"][3]["scriptPubKey"]["asm"]
    assert transaction["vout"][1]["scriptPubKey"]["stakeaddresses"]
    assert is_pos_transaction(transaction)


def test_database_is_idempotent_and_uses_wal(tmp_path):
    db = IntelligenceDB(tmp_path / "staking.sqlite3")
    assert db.connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    data = {"captured_at": "2026-11-04T00:00:00+00:00", "wallet_name": "ghostmain", "rpc_status": "OK"}
    db.save_snapshot(data)
    db.save_snapshot(data)
    assert db.connection.execute("SELECT count(*) FROM staking_snapshots").fetchone()[0] == 1
    db.close()


def test_snapshot_preserves_missing_values_as_null(tmp_path):
    calls = []

    def rpc(method, args):
        calls.append(method)
        return ({"chain": "main"} if method == "getblockchaininfo" else ({"enabled": True} if method == "getstakinginfo" else {}), None)

    db = IntelligenceDB(tmp_path / "staking.sqlite3")
    result = collect_snapshot(db, rpc)
    row = db.connection.execute("SELECT * FROM staking_snapshots").fetchone()
    assert result["network"] == "main"
    assert row["wallet_weight"] is None
    assert set(calls) == {"getblockchaininfo", "getstakinginfo", "getbalances"}


def test_block_scan_is_idempotent(tmp_path):
    def rpc(method, args):
        if method == "getblockchaininfo":
            return ({"chain": "main", "blocks": 10}, None)
        if method == "getblockhash":
            return ("h10", None)
        return ({"hash": "h10", "height": 10, "previousblockhash": "h9", "time": 1, "confirmations": 1, "tx": []}, None)

    db = IntelligenceDB(tmp_path / "staking.sqlite3")
    assert scan_block(db, rpc) == {"height": 10, "hash": "h10", "is_pos": None, "coinstake_txid": None}
    scan_block(db, rpc)
    assert db.connection.execute("SELECT count(*) FROM chain_blocks").fetchone()[0] == 1
    assert db.connection.execute("SELECT count(*) FROM block_validation_events").fetchone()[0] == 1


def test_chain_block_persists_rpc_transaction_count(tmp_path):
    db = IntelligenceDB(tmp_path / "tx-count.sqlite3")
    db.save_block({"height": 1, "hash": "h1", "nTx": 1, "tx": [{"txid": "t1"}]}, "main", False, None)
    assert db.connection.execute("SELECT tx_count FROM chain_blocks").fetchone()[0] == 1


def test_chain_block_uses_complete_transaction_array_when_ntx_missing(tmp_path):
    db = IntelligenceDB(tmp_path / "tx-array.sqlite3")
    db.save_block({"height": 1, "hash": "h1", "tx": [{"txid": "t1"}, {"txid": "t2"}]}, "main", False, None)
    assert db.connection.execute("SELECT tx_count FROM chain_blocks").fetchone()[0] == 2


def test_chain_block_keeps_unknown_transaction_count_null(tmp_path):
    db = IntelligenceDB(tmp_path / "tx-unknown.sqlite3")
    db.save_block({"height": 1, "hash": "h1", "tx": None}, "main", False, None)
    assert db.connection.execute("SELECT tx_count FROM chain_blocks").fetchone()[0] is None


def test_pos_detection_uses_ghost_coinstake_opcode():
    tx = {"txid": "stake", "vin": [], "vout": [{"scriptPubKey": {"type": "data", "asm": "OP_ISCOINSTAKE 01"}}]}
    assert is_pos_transaction(tx) is True


def test_pos_detection_rejects_pow_and_incomplete_transactions():
    assert is_pos_transaction({"txid": "pow", "vout": [{"scriptPubKey": {"asm": "OP_RETURN 01"}}]}) is False
    assert is_pos_transaction({"txid": "incomplete"}) is False
    assert is_pos_transaction({"txid": "substring", "vout": [{"scriptPubKey": {"asm": "NOT_OP_ISCOINSTAKE"}}]}) is False


def test_real_ghost_pos_fixture_fragment_is_detected():
    fixture = Path(__file__).parent / "fixtures" / "ghost_pos_block_1658462_fragment.json"
    block = json.loads(fixture.read_text())
    assert block["hash"] == "20a4ab0e868c2667ccebee4a7c6f105f9320f5e510a9c32ef3371a13691ee173"
    assert block["height"] == 1658462
    assert is_pos_transaction(block["tx"][0]) is True


def test_real_ghost_pos_fixture_is_explicitly_only_a_fragment():
    fixture = Path(__file__).parent / "fixtures" / "ghost_pos_block_1658462_fragment.json"
    block = json.loads(fixture.read_text())
    assert "time" not in block
    assert "stakeaddresses" not in block["tx"][0]["vout"][1]["scriptPubKey"]


def test_scan_catch_up_external_lock_contract_skips_recursive_instance_lock(tmp_path):
    from ghostnode.intelligence.collectors import scan_catch_up
    path = tmp_path / "external-lock.sqlite3"
    with IntelligenceDB(path) as db:
        result = scan_catch_up(
            db,
            lambda method, args: (({"blocks": 1, "bestblockhash": "h1"}, None)
                                  if method == "getblockchaininfo" else (None, "unused")),
            external_lock=True,
        )
    assert result["baseline"] is True
    assert not Path(str(path) + ".lock.instance").exists()


def test_catch_up_is_sequential_and_resumes_after_rpc_failure(tmp_path):
    from ghostnode.intelligence.collectors import scan_catch_up
    calls = {"blocks": 0, "fail": True}

    def rpc(method, args):
        if method == "getblockchaininfo":
            return ({"blocks": 3}, None)
        if method == "getblockhash":
            return (f"h{args[0]}", None)
        calls["blocks"] += 1
        if calls["fail"] and args[0] == "h2":
            return (None, "timeout")
        height = int(args[0][1:]) if isinstance(args[0], str) else 0
        return ({"hash": args[0], "height": height, "previousblockhash": f"h{height - 1}" if height else None, "tx": []}, None)

    db = IntelligenceDB(tmp_path / "staking.sqlite3")
    db.save_block({"hash": "h0", "height": 0, "previousblockhash": None, "tx": []}, "main", False, None)
    assert scan_catch_up(db, rpc)["status"] == "UNKNOWN"
    assert db.state("main")["last_scanned_height"] == 1
    calls["fail"] = False
    assert scan_catch_up(db, rpc)["status"] == "OK"
    assert db.state("main")["last_scanned_height"] == 3


def test_catch_up_batch_size_limits_progress_without_gaps(tmp_path):
    from ghostnode.intelligence.collectors import scan_catch_up

    def rpc(method, args):
        if method == "getblockchaininfo": return ({"blocks": 10}, None)
        if method == "getblockhash": return (f"h{args[0]}", None)
        height = int(args[0][1:])
        return ({"hash": args[0], "height": height,
                 "previousblockhash": f"h{height - 1}" if height else None, "tx": []}, None)

    db = IntelligenceDB(tmp_path / "batches.sqlite3")
    db.save_block({"hash": "h0", "height": 0, "previousblockhash": None, "tx": []}, "main", False, None)
    for expected in (3, 3, 3, 1):
        result = scan_catch_up(db, rpc, batch_size=3)
        assert result["processed"] == expected
    assert db.state("main")["last_scanned_height"] == 10
    assert db.connection.execute("SELECT count(*) FROM chain_blocks").fetchone()[0] == 11


def test_process_lock_rejects_second_instance(tmp_path):
    lock_path = tmp_path / "collector.lock"
    with CollectorLock(lock_path):
        try:
            with CollectorLock(lock_path):
                assert False, "second lock unexpectedly acquired"
        except RuntimeError:
            pass


def test_multi_block_reorg_preserves_old_branch_and_processes_new_branch(tmp_path):
    from ghostnode.intelligence.collectors import scan_catch_up
    old = {
        0: ("a0", None), 1: ("a1", "a0"), 2: ("a2", "a1"), 3: ("a3", "a2"),
    }
    current = dict(old)
    current.update({2: ("b2", "a1"), 3: ("b3", "b2"), 4: ("b4", "b3")})
    tip = {"height": 3}

    def rpc(method, args):
        if method == "getblockchaininfo":
            return ({"blocks": tip["height"], "bestblockhash": current[tip["height"]][0]}, None)
        if method == "getblockhash":
            return (current[args[0]][0], None)
        h = next(h for h, pair in current.items() if pair[0] == args[0])
        return ({"hash": args[0], "height": h, "previousblockhash": current[h][1], "tx": []}, None)

    db = IntelligenceDB(tmp_path / "staking.sqlite3")
    for h in range(4):
        db.save_block({"hash": old[h][0], "height": h, "previousblockhash": old[h][1], "tx": []}, "main", False, None)
    tip["height"] = 4
    result = scan_catch_up(db, rpc, batch_size=2)
    assert result["status"] == "OK"
    assert result["processed"] == 2
    assert scan_catch_up(db, rpc, batch_size=2)["processed"] == 1
    assert db.connection.execute("SELECT count(*) FROM reorg_events").fetchone()[0] == 1
    assert db.connection.execute("SELECT count(*) FROM chain_blocks WHERE hash IN ('a2','a3') AND is_active=0").fetchone()[0] == 2
    assert db.connection.execute("SELECT count(*) FROM chain_blocks WHERE hash IN ('b2','b3','b4') AND is_active=1").fetchone()[0] == 3
    assert db.state("main")["tip_hash"] == "b4"


def test_counters_can_be_rebuilt_from_source_tables(tmp_path):
    db = IntelligenceDB(tmp_path / "staking.sqlite3")
    for h in range(3):
        db.save_block({"hash": f"h{h}", "height": h, "previousblockhash": None, "tx": []}, "main", h == 2, None)
    counters = db.rebuild_validation_counters("main")
    assert counters["observed_blocks"] == 3
    assert counters["active_chain_blocks"] == 3
    assert counters["pos_blocks"] == 1


def _hold_lock(path):
    from ghostnode.intelligence.lock import CollectorLock
    with CollectorLock(path):
        time.sleep(0.5)


def _kill_after_commit(db_path, lock_path):
    from ghostnode.intelligence.db import IntelligenceDB
    from ghostnode.intelligence.lock import CollectorLock
    db = IntelligenceDB(db_path)
    with CollectorLock(lock_path):
        db.save_block({"hash": "committed", "height": 1, "previousblockhash": None, "tx": []}, "main", False, None)
        db.close()
        os.kill(os.getpid(), signal.SIGKILL)


def test_true_parallel_process_lock(tmp_path):
    path = str(tmp_path / "parallel.lock")
    process = multiprocessing.Process(target=_hold_lock, args=(path,))
    process.start()
    time.sleep(0.1)
    try:
        with __import__("pytest").raises(RuntimeError):
            with CollectorLock(path):
                pass
    finally:
        process.join(2)
    assert process.exitcode == 0


def test_sigkill_releases_lock_and_preserves_committed_data(tmp_path):
    db_path = str(tmp_path / "killed.sqlite3")
    lock_path = str(tmp_path / "killed.lock")
    process = multiprocessing.Process(target=_kill_after_commit, args=(db_path, lock_path))
    process.start()
    process.join(3)
    assert process.exitcode == -signal.SIGKILL
    with IntelligenceDB(db_path) as db:
        assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.connection.execute("SELECT hash FROM chain_blocks").fetchone()[0] == "committed"
        with CollectorLock(lock_path):
            pass


def test_integrity_check_after_restart(tmp_path):
    path = tmp_path / "staking.sqlite3"
    with IntelligenceDB(path) as db:
        db.save_block({"hash": "h", "height": 1, "previousblockhash": None, "tx": []}, "main", False, None)
        assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with IntelligenceDB(path) as db:
        assert db.connection.execute("SELECT count(*) FROM chain_blocks").fetchone()[0] == 1


def test_scanner_integrates_wallet_reward_without_txindex(tmp_path):
    from ghostnode.intelligence.collectors import scan_catch_up
    calls = []

    def rpc(method, args):
        calls.append(method)
        if method == "getblockchaininfo":
            return ({"blocks": 1}, None)
        if method == "getblockhash":
            return ("b1", None)
        if method == "getblock":
            return ({"hash": "b1", "height": 1, "previousblockhash": "b0", "tx": [{"txid": "tx1", "is_coinstake": True}]}, None)
        if method == "getblockreward":
            return (None, "Requires -txindex enabled")
        if method == "listtransactions":
            return ([{"txid": "tx1", "blockhash": "b1", "category": "stake", "reward": "1.0", "vout": 1, "confirmations": 2}], None)
        raise AssertionError(method)

    db = IntelligenceDB(tmp_path / "scan.sqlite3")
    db.save_block({"hash": "b0", "height": 0, "previousblockhash": None, "tx": []}, "main", False, None)
    result = scan_catch_up(db, rpc, maturity_depth=100)
    assert result["status"] == "OK"
    assert db.connection.execute("SELECT status FROM staking_rewards").fetchone()[0] == "IMMATURE"
    assert "getblockreward" in calls


def test_scanner_fixture_flows_through_adapter_without_fabricated_income(tmp_path):
    from ghostnode.intelligence.collectors import scan_catch_up
    fixture = json.loads((Path(__file__).parent / "fixtures/ghost_pos_block_1658759.json").read_text())

    def rpc(method, args):
        if method == "getblockchaininfo": return ({"blocks": 1658759}, None)
        if method == "getblockhash": return (fixture["hash"], None)
        if method == "getblock": return (fixture, None)
        if method == "getblockreward": return (None, "Requires -txindex enabled")
        if method == "listtransactions":
            return ([{"txid": fixture["tx"][0]["txid"], "blockhash": fixture["hash"],
                      "category": "stake", "reward": "1.0", "vout": 1, "confirmations": 2}], None)
        if method == "getrawtransaction":
            return ({"txid": args[0], "vout": [{}, {}, {"value": 1500.0,
                      "scriptPubKey": {"addresses": ["external"]}}]}, None)
        if method == "getaddressinfo": return ({"ismine": False, "solvable": True}, None)
        raise AssertionError(method)

    db = IntelligenceDB(tmp_path / "fixture-scan.sqlite3")
    db.save_block({"hash": fixture["previousblockhash"], "height": 1658758,
                   "previousblockhash": "ancestor", "tx": []}, "main", False, None)
    result = scan_catch_up(db, rpc, maturity_depth=100)
    assert result["processed"] == 1
    reward = db.connection.execute("SELECT status,wallet_reward_atomic,data_completeness FROM staking_rewards").fetchone()
    assert reward[0] == "UNVERIFIED"
    assert reward[1] is None
    assert reward[2] in {"PARTIAL", "UNKNOWN"}
    assert db.connection.execute("SELECT count(*) FROM reward_inputs").fetchone()[0] == 1
    assert db.connection.execute("SELECT count(*) FROM reward_outputs").fetchone()[0] == 4


def test_first_scan_records_baseline_without_historical_backfill(tmp_path):
    from ghostnode.intelligence.collectors import scan_catch_up

    def rpc(method, args):
        if method == "getblockchaininfo":
            return ({"blocks": 99, "bestblockhash": "h99"}, None)
        raise AssertionError(method)

    db = IntelligenceDB(tmp_path / "baseline.sqlite3")
    result = scan_catch_up(db, rpc)
    assert result == {"status": "OK", "processed": 0, "height": 99, "baseline": True}
    assert db.state("main")["last_scanned_height"] == 99
    assert db.connection.execute("SELECT validation_state FROM block_validation_events").fetchone()[0] == "BASELINE"


def test_reward_failure_does_not_advance_chain_state(tmp_path):
    db = IntelligenceDB(tmp_path / "atomic.sqlite3")
    with __import__("pytest").raises(RuntimeError):
        db.save_block_with_reward(
            {"hash": "h1", "height": 1, "previousblockhash": None, "tx": []},
            "main", True, "tx1", lambda _db: (_ for _ in ()).throw(RuntimeError("reward failed")),
        )
    assert db.connection.execute("SELECT count(*) FROM chain_blocks").fetchone()[0] == 0
    assert db.state("main") is None


def test_pending_block_retry_updates_validation_event(tmp_path):
    db = IntelligenceDB(tmp_path / "pending.sqlite3")
    block = {"hash": "h1", "height": 1, "previousblockhash": None, "tx": []}
    db.save_block_pending(block, "main", True, "tx1")
    assert db.connection.execute("SELECT validation_state FROM block_validation_events").fetchone()[0] == "PENDING"
    db.save_block_with_reward(block, "main", True, "tx1", lambda _db: "UNVERIFIED")
    assert db.connection.execute("SELECT validation_state FROM block_validation_events").fetchone()[0] == "OBSERVED"
    assert db.state("main")["last_scanned_height"] == 1


def test_listtransactions_is_paged_and_deduplicated(tmp_path):
    from ghostnode.intelligence.collectors import scan_catch_up
    calls = []
    page = [{"txid": f"tx{i}", "blockhash": "b1", "vout": i,
             "category": "stake", "reward": "1", "confirmations": 1} for i in range(1000)]

    def rpc(method, args):
        calls.append((method, args))
        if method == "getblockchaininfo": return ({"blocks": 1}, None)
        if method == "getblockhash": return ("b1", None)
        if method == "getblock": return ({"hash": "b1", "height": 1, "previousblockhash": "b0",
                                           "tx": [{"txid": "stake-tx", "is_coinstake": True}]}, None)
        if method == "getblockreward": return (None, "txindex disabled")
        if method == "listtransactions":
            return (page if args[2] == 0 else page[:1], None)
        raise AssertionError(method)

    db = IntelligenceDB(tmp_path / "paged.sqlite3")
    db.save_block({"hash": "b0", "height": 0, "previousblockhash": None, "tx": []}, "main", False, None)
    result = scan_catch_up(db, rpc, maturity_depth=100)
    assert result["status"] == "OK"
    assert [args[2] for method, args in calls if method == "listtransactions"] == [0, 1000]


def test_transaction_history_limit_is_explicit_and_keeps_cursor(tmp_path):
    from ghostnode.intelligence.collectors import MAX_TRANSACTION_PAGES, scan_catch_up

    def rpc(method, args):
        if method == "getblockchaininfo": return ({"blocks": 1}, None)
        if method == "getblockhash": return ("b1", None)
        if method == "getblock": return ({"hash": "b1", "height": 1, "previousblockhash": "b0",
                                           "tx": [{"txid": "stake-tx", "is_coinstake": True}]}, None)
        if method == "getblockreward": return (None, "txindex disabled")
        if method == "listtransactions":
            return ([{"txid": f"tx{args[2]}", "vout": 0, "blockhash": "b1"}] * 1000, None)
        raise AssertionError(method)

    db = IntelligenceDB(tmp_path / "limit.sqlite3")
    db.save_block({"hash": "b0", "height": 0, "previousblockhash": None, "tx": []}, "main", False, None)
    result = scan_catch_up(db, rpc, batch_size=1)
    assert result["status"] == "UNKNOWN"
    assert result["history_status"] == "LIMIT_REACHED"
    assert db.state("main")["last_scanned_height"] == 0
    assert MAX_TRANSACTION_PAGES == 20


def test_failed_transaction_rolls_back(tmp_path):
    db = IntelligenceDB(tmp_path / "staking.sqlite3")
    with __import__("pytest").raises(sqlite3.IntegrityError):
        db.save_block({"height": 1, "hash": "h", "previousblockhash": None}, None, None, None)
    assert db.connection.execute("SELECT count(*) FROM chain_blocks").fetchone()[0] == 0
