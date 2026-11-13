from __future__ import annotations

from click.testing import CliRunner

from ghostnode.cli import cli
from ghostnode.config import Config
from ghostnode.intelligence.runner import CollectorRunner


def make_runner(tmp_path):
    return CollectorRunner(Config(cli_path="unused", datadir=str(tmp_path), timeout=0.1),
                           tmp_path / "intelligence.sqlite3", block_interval=60,
                           snapshot_interval=900, batch_size=3)


def test_collector_cli_is_exposed():
    result = CliRunner().invoke(cli, ["collector", "--help"])
    assert result.exit_code == 0
    assert "--check" in result.output
    assert "--once" in result.output


def test_preflight_failure_does_not_open_database(tmp_path):
    item = make_runner(tmp_path)
    item._rpc = lambda method, args: (None, "unavailable")
    assert item.check() == 1
    assert not (tmp_path / "intelligence.sqlite3").exists()


def test_preflight_getstakinginfo_does_not_require_wallet_context(tmp_path, monkeypatch):
    item = make_runner(tmp_path)
    calls = []

    def fake_call(method, config, wallet=None):
        calls.append((method, wallet))
        return ({}, None)

    monkeypatch.setattr("ghostnode.intelligence.runner._call", fake_call)
    assert item.preflight() == (True, None)
    assert calls == [("getblockchaininfo", None), ("getstakinginfo", None)]


def test_runner_wallet_context_does_not_duplicate_staking_argument(tmp_path, monkeypatch):
    item = make_runner(tmp_path)
    seen = []

    def fake_call(method, config, wallet=None, args=None):
        seen.append((method, wallet, args))
        return ({}, None)

    monkeypatch.setattr("ghostnode.intelligence.runner._call", fake_call)
    item._rpc("getstakinginfo", ["ghostmain"])
    assert seen == [("getstakinginfo", "ghostmain", None)]


def test_once_runs_one_snapshot_and_one_batch_after_preflight(tmp_path):
    item = make_runner(tmp_path)
    calls = []
    item.preflight = lambda: (True, None)
    item.run_snapshot = lambda: calls.append("snapshot")
    item.run_blocks = lambda: calls.append("blocks")
    assert item.once() == 0
    assert calls == ["snapshot", "blocks"]


def test_once_records_successful_run(tmp_path):
    item = make_runner(tmp_path)
    item.preflight = lambda: (True, None)
    item.run_snapshot = lambda: {"rpc_status": "OK"}
    item.run_blocks = lambda: {"status": "OK", "processed": 0, "height": 123}
    assert item.once() == 0
    from ghostnode.intelligence.db import IntelligenceDB
    with IntelligenceDB(tmp_path / "intelligence.sqlite3") as db:
        row = db.connection.execute("SELECT * FROM collector_runs").fetchone()
        assert row["collector_name"] == "collector_once"
        assert row["status"] == "SUCCESS"
        assert row["finished_at"] is not None


def test_once_records_failed_run_without_secrets(tmp_path):
    item = make_runner(tmp_path)
    item.preflight = lambda: (True, None)
    item.run_snapshot = lambda: {"rpc_status": "OK"}
    item.run_blocks = lambda: (_ for _ in ()).throw(RuntimeError("safe diagnostic"))
    assert item.once() == 1
    from ghostnode.intelligence.db import IntelligenceDB
    with IntelligenceDB(tmp_path / "intelligence.sqlite3") as db:
        row = db.connection.execute("SELECT * FROM collector_runs").fetchone()
        assert row["status"] == "PARTIAL"
        assert row["error_code"] == "RuntimeError"


def test_preflight_failure_is_recorded_without_snapshot(tmp_path):
    item = make_runner(tmp_path)
    item.preflight = lambda: (False, "RPC password=super-secret")
    called = []
    item.run_snapshot = lambda: called.append("snapshot")
    assert item.once() == 1
    assert called == []
    from ghostnode.intelligence.db import IntelligenceDB
    with IntelligenceDB(tmp_path / "intelligence.sqlite3") as db:
        row = db.connection.execute("SELECT * FROM collector_runs").fetchone()
        assert row["status"] == "FAILED"
        assert row["error_message"] == "RPC_PREFLIGHT_FAILED"
        assert db.state("main") is None


def test_recovery_marks_dead_process_only(tmp_path):
    from ghostnode.intelligence.db import IntelligenceDB
    path = tmp_path / "intelligence.sqlite3"
    with IntelligenceDB(path) as db:
        dead = db.start_collector_run("old", "2026-11-04T00:00:00+00:00")
        db.connection.execute("UPDATE collector_runs SET owner_pid=? WHERE id=?", (999999999, dead))
        db.connection.commit()
        live = db.start_collector_run("live")
        from ghostnode.intelligence.process_identity import current_identity
        pid, ticks, boot = current_identity()
        db.connection.execute("UPDATE collector_runs SET owner_pid=?, owner_start_ticks=?, owner_boot_id=? WHERE id=?", (pid, ticks, boot, live))
        db.connection.commit()
        assert db.recover_interrupted_runs() == 1
        old = db.connection.execute("SELECT * FROM collector_runs WHERE id=?", (dead,)).fetchone()
        current = db.connection.execute("SELECT * FROM collector_runs WHERE id=?", (live,)).fetchone()
        assert old["status"] == "FAILED"
        assert old["error_message"] == "INTERRUPTED_BY_PROCESS_RESTART"
        assert current["status"] == "RUNNING"


def test_recovery_is_fail_safe_for_unknown_and_detects_reuse(tmp_path, monkeypatch):
    from ghostnode.intelligence.db import IntelligenceDB
    path = tmp_path / "identity.sqlite3"
    with IntelligenceDB(path) as db:
        unknown = db.start_collector_run("unknown")
        reused = db.start_collector_run("reused")
        db.connection.execute("UPDATE collector_runs SET owner_pid=10, owner_start_ticks=20, owner_boot_id='boot-a' WHERE id=?", (unknown,))
        db.connection.execute("UPDATE collector_runs SET owner_pid=11, owner_start_ticks=20, owner_boot_id='boot-a' WHERE id=?", (reused,))
        db.connection.commit()
        states = {10: ("UNKNOWN", None, None), 11: ("ACTIVE", 21, "boot-a")}
        monkeypatch.setattr("ghostnode.intelligence.process_identity.process_identity", lambda pid: states[pid])
        assert db.recover_interrupted_runs() == 1
        assert db.connection.execute("SELECT status FROM collector_runs WHERE id=?", (unknown,)).fetchone()[0] == "RUNNING"
        assert db.connection.execute("SELECT status FROM collector_runs WHERE id=?", (reused,)).fetchone()[0] == "FAILED"


def test_worker_stops_after_one_run_without_backlog(tmp_path):
    item = make_runner(tmp_path)
    item.preflight = lambda: (True, None)
    seen = []

    def operation():
        seen.append("run")
        item.stop_event.set()

    item._worker("block scan", 60, operation)
    assert seen == ["run"]


def test_simulated_thirty_minute_scanner_has_bounded_cycles(tmp_path, monkeypatch):
    item = make_runner(tmp_path)
    # This test measures monotonic scheduling only; persistence is covered by
    # the dedicated collector-run tests above.
    item._start_run = lambda *args, **kwargs: 1
    item._finish_run = lambda *args, **kwargs: None
    clock = [0.0]
    class FakeEvent:
        def __init__(self): self.stopped = False
        def is_set(self): return self.stopped
        def set(self): self.stopped = True
        def wait(self, seconds): clock[0] += seconds
    item.stop_event = FakeEvent()
    monkeypatch.setattr("ghostnode.intelligence.runner.time.monotonic", lambda: clock[0])
    item.preflight = lambda: (True, None)
    calls = []
    def operation():
        calls.append(clock[0])
        if len(calls) >= 31 * 30:
            item.stop_event.set()
    item._worker("block scan", 60, operation)
    assert len(calls) == 930
    assert calls[0] == 0.0
    assert calls[-1] == 929 * 60


def test_signal_handler_requests_graceful_shutdown(tmp_path):
    import signal
    from ghostnode.intelligence.runner import install_signal_handlers
    item = make_runner(tmp_path)
    install_signal_handlers(item)
    signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    assert item.stop_event.is_set()


def test_block_plan_revalidates_chain_state_before_write(tmp_path):
    from ghostnode.intelligence.collectors import StalePlan, apply_block_plan, prepare_block_plan
    from ghostnode.intelligence.db import IntelligenceDB

    db_path = tmp_path / "plan.sqlite3"
    with IntelligenceDB(db_path) as db:
        db.save_block({"hash": "h0", "height": 0, "previousblockhash": None, "tx": []}, "main", False, None)

    def rpc(method, args):
        if method == "getblockchaininfo": return ({"blocks": 1}, None)
        if method == "getblockhash": return ("h1", None)
        if method == "getblock": return ({"hash": "h1", "height": 1, "previousblockhash": "h0", "tx": []}, None)
        raise AssertionError(method)

    plan = prepare_block_plan(db_path, rpc, batch_size=1)
    with IntelligenceDB(db_path) as db:
        db.save_block({"hash": "h0b", "height": 0, "previousblockhash": None, "tx": []}, "main", False, None)
        try:
            apply_block_plan(db, plan)
        except StalePlan:
            pass
        else:
            raise AssertionError("stale plan was applied")


def test_block_plan_rejects_tip_hash_mismatch_without_writing(tmp_path):
    from ghostnode.intelligence.collectors import StalePlan, apply_block_plan, prepare_block_plan
    from ghostnode.intelligence.db import IntelligenceDB

    db_path = tmp_path / "tip.sqlite3"
    with IntelligenceDB(db_path) as db:
        db.save_block({"hash": "h0", "height": 0, "previousblockhash": None, "tx": []}, "main", False, None)

    def rpc(method, args):
        if method == "getblockchaininfo": return ({"blocks": 1}, None)
        if method == "getblockhash": return ("h1", None)
        if method == "getblock": return ({"hash": "h1", "height": 1, "previousblockhash": "h0", "tx": []}, None)
        raise AssertionError(method)

    plan = prepare_block_plan(db_path, rpc, batch_size=1)
    with IntelligenceDB(db_path) as db:
        try:
            apply_block_plan(db, plan, validated_tip_hash="different")
        except StalePlan:
            pass
        else:
            raise AssertionError("tip mismatch was accepted")
        assert db.state("main")["last_scanned_height"] == 0


def test_block_plan_accepts_matching_tip_hash(tmp_path):
    from ghostnode.intelligence.collectors import apply_block_plan, prepare_block_plan
    from ghostnode.intelligence.db import IntelligenceDB

    db_path = tmp_path / "tip-ok.sqlite3"
    with IntelligenceDB(db_path) as db:
        db.save_block({"hash": "h0", "height": 0, "previousblockhash": None, "tx": []}, "main", False, None)

    def rpc(method, args):
        if method == "getblockchaininfo": return ({"blocks": 1}, None)
        if method == "getblockhash": return ("h1", None)
        if method == "getblock": return ({"hash": "h1", "height": 1, "previousblockhash": "h0", "tx": []}, None)
        raise AssertionError(method)

    plan = prepare_block_plan(db_path, rpc, batch_size=1)
    with IntelligenceDB(db_path) as db:
        result = apply_block_plan(db, plan, validated_tip_hash="h1")
        assert result["processed"] == 1


def _reorg_fixture(tmp_path):
    from ghostnode.intelligence.collectors import BlockScanPlan
    from ghostnode.intelligence.db import IntelligenceDB
    db_path = tmp_path / "reorg-fault.sqlite3"
    with IntelligenceDB(db_path) as db:
        for height, block_hash, previous in ((0, "a0", None), (1, "a1", "a0"),
                                             (2, "a2", "a1"), (3, "a3", "a2")):
            db.save_block({"hash": block_hash, "height": height, "previousblockhash": previous, "tx": []},
                          "main", False, None)
        state = db.state("main")
    blocks = tuple({"hash": h, "height": n, "previousblockhash": p, "tx": []}
                   for n, h, p in ((2, "b2", "a1"), (3, "b3", "b2")))
    plan = BlockScanPlan("main", 3,
                         (state["tip_height"], state["tip_hash"], state["last_scanned_height"]),
                         blocks, (({}, [], "COMPLETE"), ({}, [], "COMPLETE")),
                         ancestor={"height": 1, "hash": "a1"}, old_state=state)
    return db_path, plan


def test_reorg_faults_roll_back_orphaning_record_and_new_branch(tmp_path, monkeypatch):
    from ghostnode.intelligence.collectors import apply_block_plan
    from ghostnode.intelligence.db import IntelligenceDB

    for point in ("orphaning", "record_reorg", "new_branch"):
        db_path, plan = _reorg_fixture(tmp_path / point)
        with IntelligenceDB(db_path) as db:
            if point == "orphaning":
                original = db.mark_orphaned_from
                def fail(*args, **kwargs):
                    original(*args, **kwargs)
                    raise RuntimeError("after orphaning")
                monkeypatch.setattr(db, "mark_orphaned_from", fail)
            elif point == "record_reorg":
                original = db.record_reorg
                def fail(*args, **kwargs):
                    original(*args, **kwargs)
                    raise RuntimeError("after reorg record")
                monkeypatch.setattr(db, "record_reorg", fail)
            else:
                original = db._save_block_in_transaction
                def fail(*args, **kwargs):
                    original(*args, **kwargs)
                    raise RuntimeError("during new branch")
                monkeypatch.setattr(db, "_save_block_in_transaction", fail)
            try:
                apply_block_plan(db, plan, validated_tip_hash="b3")
            except RuntimeError:
                pass
            else:
                raise AssertionError(point)
            assert db.state("main")["tip_hash"] == "a3"
            assert db.connection.execute("SELECT count(*) FROM reorg_events").fetchone()[0] == 0
            assert db.connection.execute("SELECT count(*) FROM chain_blocks WHERE is_active=0").fetchone()[0] == 0
            assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        monkeypatch.undo()
        with IntelligenceDB(db_path) as db:
            result = apply_block_plan(db, plan, validated_tip_hash="b3")
            assert result["processed"] == 2
            assert db.connection.execute("SELECT count(*) FROM reorg_events").fetchone()[0] == 1
            assert db.connection.execute("SELECT count(*) FROM chain_blocks WHERE is_active=0").fetchone()[0] == 2


def test_reorg_fault_during_reward_rolls_back_everything(tmp_path, monkeypatch):
    from ghostnode.intelligence import collectors
    from ghostnode.intelligence.collectors import BlockScanPlan, apply_block_plan
    from ghostnode.intelligence.db import IntelligenceDB

    db_path, base = _reorg_fixture(tmp_path / "reward-fault")
    block = {"hash": "b2", "height": 2, "previousblockhash": "a1",
             "tx": [{"txid": "stake-tx", "is_coinstake": True}]}
    plan = BlockScanPlan(base.network, 2, base.expected_state, (block,),
                         (({"hash": "b2", "height": 2, "coinstake": "stake-tx"},
                           [{"txid": "stake-tx", "blockhash": "b2", "category": "stake",
                             "reward": "1", "vout": 0, "confirmations": 1}], "COMPLETE"),),
                         ancestor={"height": 1, "hash": "a1"}, old_state=base.old_state)
    monkeypatch.setattr(collectors, "_track_reward_in_transaction",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("reward write")))
    with IntelligenceDB(db_path) as db:
        try:
            apply_block_plan(db, plan, validated_tip_hash="b2")
        except RuntimeError:
            pass
        else:
            raise AssertionError("reward fault was accepted")
        assert db.state("main")["tip_hash"] == "a3"
        assert db.connection.execute("SELECT count(*) FROM staking_rewards").fetchone()[0] == 0
        assert db.connection.execute("SELECT count(*) FROM chain_blocks WHERE is_active=0").fetchone()[0] == 0
        assert db.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
