from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ghostnode.intelligence.db import IntelligenceDB
from ghostnode.intelligence.rewards import financial_summary
from ghostnode.presentation import active_label, format_block_time, pos_label, short_hash


def _db(path: str | Path) -> IntelligenceDB:
    target = Path(path).expanduser()
    # Dashboard reads must never create, migrate, WAL-enable, or otherwise write the DB.
    db = object.__new__(IntelligenceDB)
    db.path = target
    db.connection = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    db.connection.row_factory = sqlite3.Row
    return db


def _empty() -> dict[str, Any]:
    return {"status": "NOT STARTED", "data": [], "message": None}


def _error() -> dict[str, Any]:
    return {"status": "UNKNOWN", "data": [], "message": "Intelligence data unavailable"}


def overview(path: str | Path) -> dict[str, Any]:
    if not Path(path).expanduser().exists():
        return {"status": "NOT STARTED", "data": {"rewards": {}, "blocks": {}, "staking": None}}
    try:
        with _db(path) as db:
            snapshot = db.connection.execute("SELECT * FROM staking_snapshots ORDER BY captured_at DESC LIMIT 1").fetchone()
            counters = db.connection.execute("SELECT * FROM validation_counters LIMIT 1").fetchone()
            chain_state = db.connection.execute("SELECT * FROM chain_state LIMIT 1").fetchone()
            baseline = db.connection.execute(
                "SELECT * FROM staking_events WHERE event_type='baseline' ORDER BY detected_at DESC LIMIT 1"
            ).fetchone()
            rewards = financial_summary(db)
            status = "OK" if snapshot or counters else ("BASELINE ESTABLISHED" if baseline else "NOT STARTED")
            return {"status": status, "data": {
                "staking": dict(snapshot) if snapshot else None,
                "rewards": rewards,
                "blocks": dict(counters) if counters else {},
                "chain_state": dict(chain_state) if chain_state else None,
                "baseline": dict(baseline) if baseline else None,
                "last_snapshot": snapshot["captured_at"] if snapshot else None,
            }}
    except (sqlite3.Error, OSError):
        return _error()


def performance(path: str | Path, period: str = "24h", limit: int = 1000,
                now: datetime | None = None) -> dict[str, Any]:
    periods = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30), "90d": timedelta(days=90), "ALL": None}
    if period not in periods or not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 5000:
        return {"status": "ERROR", "data": [], "message": "Invalid performance parameters"}
    if not Path(path).expanduser().exists():
        return _empty()
    try:
        with _db(path) as db:
            reference = now or datetime.now(timezone.utc)
            since = None if periods[period] is None else (reference - periods[period]).isoformat(timespec="seconds")
            if since:
                rows = db.connection.execute("SELECT captured_at,network, wallet_weight,network_weight,difficulty,expected_time_seconds,balance_json FROM staking_snapshots WHERE captured_at>=? ORDER BY captured_at LIMIT ?", (since, limit)).fetchall()
            else:
                rows = db.connection.execute("SELECT captured_at,network, wallet_weight,network_weight,difficulty,expected_time_seconds,balance_json FROM staking_snapshots ORDER BY captured_at LIMIT ?", (limit,)).fetchall()
            records = [dict(row) for row in rows]
            series = {"wallet_weight": [], "network_weight": [], "network_share": [],
                      "difficulty": [], "expected_time": [], "wallet_balance": [],
                      "cumulative_confirmed_rewards": []}
            cumulative = 0
            for record in records:
                ts = record["captured_at"]
                wallet = record.get("wallet_weight")
                network = record.get("network_weight")
                if wallet is not None: series["wallet_weight"].append({"timestamp": ts, "value": wallet})
                if network is not None: series["network_weight"].append({"timestamp": ts, "value": network})
                if wallet is not None and network not in (None, 0):
                    series["network_share"].append({"timestamp": ts, "value": wallet / network * 100})
                for key, source in (("difficulty", "difficulty"), ("expected_time", "expected_time_seconds")):
                    if record.get(source) is not None: series[key].append({"timestamp": ts, "value": record[source]})
                if record.get("balance_json"):
                    try:
                        trusted = __import__("json").loads(record["balance_json"]).get("mine", {}).get("trusted")
                    except (TypeError, ValueError, AttributeError):
                        trusted = None
                    if trusted is not None: series["wallet_balance"].append({"timestamp": ts, "value": trusted})
            reward_rows = db.connection.execute(
                "SELECT created_at,wallet_reward_atomic FROM staking_rewards "
                "WHERE status='MATURED' AND data_completeness='COMPLETE' "
                "AND wallet_reward_atomic IS NOT NULL AND wallet_reward_atomic > 0 "
                "ORDER BY created_at LIMIT ?", (limit,)).fetchall()
            for reward in reward_rows:
                if isinstance(reward["wallet_reward_atomic"], int):
                    cumulative += reward["wallet_reward_atomic"]
                    series["cumulative_confirmed_rewards"].append({"timestamp": reward["created_at"], "value_atomic": cumulative})
            return {"status": "OK", "data": records, "series": series, "period": period}
    except (sqlite3.Error, OSError):
        return _error()


def rewards(path: str | Path, status: str | None = None, limit: int = 100, offset: int = 0,
            since: str | None = None, until: str | None = None) -> dict[str, Any]:
    allowed = {"DETECTED", "IDENTIFIED", "IMMATURE", "MATURED", "SPENT", "ORPHANED", "UNVERIFIED"}
    if status and status not in allowed or not isinstance(limit, int) or not 1 <= limit <= 500 or not isinstance(offset, int) or offset < 0:
        return {"status": "ERROR", "data": [], "message": "Invalid reward parameters"}
    if not Path(path).expanduser().exists():
        return _empty()
    try:
        with _db(path) as db:
            clauses, params = [], []
            if status: clauses.append("status=?"); params.append(status)
            if since: clauses.append("created_at>=?"); params.append(since)
            if until: clauses.append("created_at<=?"); params.append(until)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            rows = db.connection.execute(f"SELECT * FROM staking_rewards{where} ORDER BY created_at DESC LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
            records = [dict(row) for row in rows]
            ids = [record["event_id"] for record in records if record.get("event_id") is not None]
            history = []
            if ids:
                marks = ",".join("?" for _ in ids)
                history = [dict(row) for row in db.connection.execute(f"SELECT * FROM reward_status_history WHERE event_id IN ({marks}) ORDER BY changed_at", ids).fetchall()]
            return {"status": "OK", "data": records, "history": history, "limit": limit, "offset": offset}
    except (sqlite3.Error, OSError):
        return _error()


def blocks(path: str | Path, active: bool | None = None, pos: bool | None = None,
           wallet_produced: bool | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    if not isinstance(limit, int) or not 1 <= limit <= 500 or not isinstance(offset, int) or offset < 0:
        return {"status": "ERROR", "data": [], "message": "Invalid block parameters"}
    if not Path(path).expanduser().exists():
        return _empty()
    try:
        with _db(path) as db:
            clauses, params = [], []
            if active is not None: clauses.append("is_active=?"); params.append(int(active))
            if pos is not None: clauses.append("is_pos=?"); params.append(int(pos))
            if wallet_produced is True: clauses.append("EXISTS (SELECT 1 FROM staking_rewards r WHERE r.coinstake_txid=chain_blocks.coinstake_txid)")
            if wallet_produced is False: clauses.append("NOT EXISTS (SELECT 1 FROM staking_rewards r WHERE r.coinstake_txid=chain_blocks.coinstake_txid)")
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            rows = db.connection.execute(f"SELECT * FROM chain_blocks{where} ORDER BY height DESC LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
            completeness_row = db.connection.execute(
                """SELECT COUNT(*) AS active_blocks,
                          SUM(CASE WHEN tx_count IS NOT NULL THEN 1 ELSE 0 END) AS complete_blocks,
                          SUM(CASE WHEN tx_count IS NULL THEN 1 ELSE 0 END) AS incomplete_blocks
                   FROM chain_blocks WHERE is_active=1"""
            ).fetchone()
            active_blocks = int(completeness_row["active_blocks"] or 0)
            complete_blocks = int(completeness_row["complete_blocks"] or 0)
            incomplete_blocks = int(completeness_row["incomplete_blocks"] or 0)
            tx_completeness = {
                "active_blocks": active_blocks,
                "complete_blocks": complete_blocks,
                "incomplete_blocks": incomplete_blocks,
                "percent": round(complete_blocks / active_blocks * 100, 2) if active_blocks else None,
            }
            data = []
            for row in rows:
                item = dict(row)
                item.update({"block_time_display": format_block_time(item.get("block_time")),
                             "active_label": active_label(item.get("is_active")),
                             "pos_label": pos_label(item.get("is_pos")),
                             "tx_count_display": item.get("tx_count") if item.get("tx_count") is not None else "N/A",
                             "hash_short": short_hash(item.get("hash")),
                             "coinstake_short": short_hash(item.get("coinstake_txid"))})
                data.append(item)
            return {"status": "OK", "data": data, "limit": limit, "offset": offset,
                    "tx_completeness": tx_completeness}
    except (sqlite3.Error, OSError):
        return _error()


def collector(path: str | Path) -> dict[str, Any]:
    if not Path(path).expanduser().exists():
        return {"status": "NOT STARTED", "collector_status": "NOT_STARTED", "data": {}}
    try:
        with _db(path) as db:
            run = db.connection.execute("SELECT * FROM collector_runs ORDER BY started_at DESC LIMIT 1").fetchone()
            successful = db.connection.execute("SELECT * FROM collector_runs WHERE status='SUCCESS' ORDER BY finished_at DESC LIMIT 1").fetchone()
            state = db.connection.execute("SELECT * FROM chain_state LIMIT 1").fetchone()
            detailed_status = run["status"] if run else ("BASELINE_ESTABLISHED" if state else "NOT_STARTED")
            return {"status": "OK" if run or state else "NOT STARTED",
                    "collector_status": detailed_status, "data": {
                "last_run": dict(run) if run else None,
                "last_successful_run": dict(successful) if successful else None,
                "chain_state": dict(state) if state else None,
                "database_bytes": Path(path).stat().st_size,
                "sqlite_integrity": db.connection.execute("PRAGMA integrity_check").fetchone()[0],
            }}
    except (sqlite3.Error, OSError):
        return _error()
