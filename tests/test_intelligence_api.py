import httpx
import pytest

pytest.importorskip("fastapi")

from ghostnode import web
from ghostnode.config import Config
from ghostnode.intelligence.db import IntelligenceDB


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_intelligence_endpoints_empty_database(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "_intelligence_path", lambda: tmp_path / "missing.sqlite3")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=web.create_app(Config())), base_url="http://test")
    async with client:
        for endpoint in ("overview", "performance", "rewards", "blocks", "collector"):
            response = await client.get(f"/api/intelligence/{endpoint}")
            assert response.status_code == 200
            assert response.json()["status"] in {"NOT STARTED", "OK"}


@pytest.mark.parametrize("run_status", ["RUNNING", "SUCCESS", "PARTIAL", "FAILED"])
def test_collector_api_exposes_detailed_run_status(tmp_path, run_status):
    from ghostnode.intelligence.views import collector
    path = tmp_path / f"collector-{run_status}.sqlite3"
    with IntelligenceDB(path) as db:
        run_id = db.start_collector_run("test", started_at="2026-11-05T12:00:00+00:00",
                                        owner_pid=999999, owner_start_ticks=1, owner_boot_id="test")
        if run_status != "RUNNING":
            db.finish_collector_run(run_id, run_status, finished_at="2026-11-05T12:01:00+00:00")
    result = collector(path)
    assert result["collector_status"] == run_status
    assert result["status"] == "OK"


def test_collector_api_reports_baseline_status(tmp_path):
    from ghostnode.intelligence.views import collector
    path = tmp_path / "baseline-collector.sqlite3"
    with IntelligenceDB(path) as db:
        db.connection.execute(
            "INSERT INTO chain_state(network, tip_height, tip_hash, last_scanned_height, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("main", 1, "h1", 1, "2026-11-05T12:00:00+00:00"),
        )
        db.connection.commit()
    result = collector(path)
    assert result["collector_status"] == "BASELINE_ESTABLISHED"


@pytest.mark.anyio
async def test_intelligence_api_reads_fixture_and_limits(monkeypatch, tmp_path):
    path = tmp_path / "staking.sqlite3"
    from datetime import datetime, timezone
    captured = "2026-11-05T12:00:00+00:00"
    reference = datetime(2026, 11, 5, 13, 0, tzinfo=timezone.utc)
    with IntelligenceDB(path) as db:
        db.save_snapshot({"captured_at": captured, "wallet_name": "ghostmain", "wallet_weight": 10, "rpc_status": "OK"})
    monkeypatch.setattr(web, "_intelligence_path", lambda: path)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=web.create_app(Config(), clock=lambda: reference)), base_url="http://test")
    async with client:
        assert (await client.get("/api/intelligence/overview")).json()["status"] == "OK"
        assert (await client.get("/api/intelligence/performance?period=24h&limit=1")).json()["data"]
        assert (await client.get("/api/intelligence/performance?range=ALL&limit=1")).json()["data"]
        assert (await client.get("/api/intelligence/performance?period=bad")).json()["status"] == "ERROR"
        assert (await client.get("/api/intelligence/rewards?limit=9999")).json()["status"] == "ERROR"


def test_performance_series_and_financial_integrity(tmp_path):
    from ghostnode.intelligence.views import performance
    path = tmp_path / "staking.sqlite3"
    with IntelligenceDB(path) as db:
        for index in range(300):
            db.save_snapshot({"captured_at": f"2026-11-04T00:{index // 60:02d}:{index % 60:02d}+00:00",
                              "wallet_name": "ghostmain", "wallet_weight": index + 1,
                              "network_weight": 1000, "difficulty": 2, "expected_time_seconds": 30,
                              "rpc_status": "OK"})
    result = performance(path, "ALL", 500)
    assert result["status"] == "OK"
    assert len(result["data"]) == 300
    assert len(result["series"]["wallet_weight"]) == 300
    assert result["series"]["network_share"][0]["value"] == 0.1


def test_cumulative_confirmed_rewards_excludes_incomplete_and_orphaned(tmp_path):
    from ghostnode.intelligence.views import performance
    path = tmp_path / "rewards.sqlite3"
    with IntelligenceDB(path) as db:
        for index, status, completeness, amount in (
            (1, "MATURED", "COMPLETE", 100),
            (2, "MATURED", "PARTIAL", 200),
            (3, "ORPHANED", "COMPLETE", 300),
        ):
            db.connection.execute(
                "INSERT INTO staking_events(event_key,network,event_type,status,detected_at) VALUES(?,?,?,?,?)",
                (f"e{index}", "main", "staking_reward", status, "now"),
            )
            event_id = db.connection.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.connection.execute(
                """INSERT INTO staking_rewards(event_id,network,block_hash,coinstake_txid,wallet_name,
                   wallet_reward_atomic,spent_status,status,data_completeness,source_rpc,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id, "main", f"b{index}", f"t{index}", "ghostmain", amount,
                 "UNKNOWN", status, completeness, "fixture", "now", "now"),
            )
        db.connection.commit()
    data = performance(path, "ALL")
    assert data["series"]["cumulative_confirmed_rewards"][-1]["value_atomic"] == 100


def test_read_only_view_does_not_migrate_or_write(tmp_path):
    from ghostnode.intelligence.views import overview
    path = tmp_path / "staking.sqlite3"
    with IntelligenceDB(path) as db:
        db.save_snapshot({"captured_at": "2026-11-04T00:00:00+00:00", "wallet_name": "ghostmain", "rpc_status": "OK"})
    before = path.stat().st_mtime_ns
    overview(path)
    assert path.stat().st_mtime_ns == before


def test_template_contains_intelligence_views():
    template = (web.BASE_DIR / "templates" / "dashboard.html").read_text()
    for marker in ("Performance", "Rewards", "Chain Monitoring", "Collector", "TX", "/api/intelligence/overview", "NOT STARTED", "24h", "7d", "30d", "90d", "ALL", "selectedPeriod", "Completeness", "Block reward", "Treasury", "GVR", "source_rpc"):
        assert marker in template


def test_dashboard_chart_selection_uses_only_trusted_series():
    template = (web.BASE_DIR / "templates" / "dashboard.html").read_text()
    assert "['Network stake weight','network_weight']" in template
    assert "['Difficulty','difficulty']" in template
    assert "['Expected time','expected_time']" in template
    assert "['Cumulative confirmed rewards','cumulative_confirmed_rewards']" in template
    assert "['Wallet weight','wallet_weight']" not in template
    assert "['Network share','network_share']" not in template
    assert "['Wallet balance','wallet_balance']" not in template


def test_blocks_reports_active_transaction_count_completeness(tmp_path):
    from ghostnode.intelligence.views import blocks
    path = tmp_path / "blocks.sqlite3"
    with IntelligenceDB(path) as db:
        for height, active, tx_count in ((1, 1, 1), (2, 1, 0), (3, 1, None), (4, 0, None)):
            db.connection.execute(
                """INSERT INTO chain_blocks
                   (network,height,hash,is_active,first_seen_at,last_seen_at,tx_count)
                   VALUES(?,?,?,?,?,?,?)""",
                ("main", height, f"h{height}", active, "now", "now", tx_count),
            )
        db.connection.commit()
    result = blocks(path, active=True, limit=20)
    assert result["tx_completeness"] == {
        "active_blocks": 3, "complete_blocks": 2, "incomplete_blocks": 1, "percent": 66.67,
    }
    assert [row["tx_count_display"] for row in result["data"]] == ["N/A", 0, 1]


def test_blocks_completeness_ignores_inactive_rows(tmp_path):
    from ghostnode.intelligence.views import blocks
    path = tmp_path / "blocks-empty.sqlite3"
    with IntelligenceDB(path) as db:
        db.connection.execute(
            """INSERT INTO chain_blocks
               (network,height,hash,is_active,first_seen_at,last_seen_at,tx_count)
               VALUES(?,?,?,?,?,?,?)""", ("main", 1, "orphan", 0, "now", "now", None)
        )
        db.connection.commit()
    assert blocks(path)["tx_completeness"] == {
        "active_blocks": 0, "complete_blocks": 0, "incomplete_blocks": 0, "percent": None,
    }


def test_baseline_and_empty_rewards_are_explicit_in_api(tmp_path):
    from ghostnode.intelligence.views import overview, rewards
    path = tmp_path / "baseline.sqlite3"
    with IntelligenceDB(path) as db:
        db.connection.execute(
            "INSERT INTO chain_state(network, tip_height, tip_hash, last_scanned_height, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("main", 123, "baseline-hash", 123, "2026-11-04T00:00:00+00:00"),
        )
        db.connection.commit()
    data = overview(path)
    assert data["data"]["chain_state"]["tip_height"] == 123
    assert rewards(path)["data"] == []


def test_baseline_status_is_not_not_started(tmp_path):
    from ghostnode.intelligence.views import overview
    path = tmp_path / "baseline-status.sqlite3"
    with IntelligenceDB(path) as db:
        db.connection.execute(
            "INSERT INTO chain_state(network, tip_height, tip_hash, last_scanned_height, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("main", 10, "h10", 10, "2026-11-04T00:00:00+00:00"),
        )
        db.connection.execute(
            "INSERT INTO staking_events(event_key, network, event_type, status, detected_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            ("baseline:10", "main", "baseline", "BASELINE", "2026-11-04T00:00:00+00:00", "{}"),
        )
        db.connection.commit()
    assert overview(path)["status"] == "BASELINE ESTABLISHED"
