from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 6


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS staking_snapshots (
 id INTEGER PRIMARY KEY, captured_at TEXT NOT NULL, network TEXT, wallet_name TEXT NOT NULL,
 enabled INTEGER, staking INTEGER, cause TEXT, wallet_weight INTEGER, network_weight INTEGER,
 difficulty REAL, expected_time_seconds INTEGER, min_stakeable_depth INTEGER,
 balance_json TEXT, rpc_latency_ms REAL, rpc_status TEXT NOT NULL, execution_ms REAL,
 UNIQUE(wallet_name, captured_at)
);
CREATE TABLE IF NOT EXISTS chain_blocks (
 id INTEGER PRIMARY KEY, network TEXT NOT NULL, height INTEGER NOT NULL, hash TEXT NOT NULL,
 previous_hash TEXT, block_time INTEGER, confirmations INTEGER, is_active INTEGER NOT NULL DEFAULT 1,
 is_pos INTEGER, coinstake_txid TEXT, tx_count INTEGER, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
 UNIQUE(network, hash), UNIQUE(network, height, hash)
);
CREATE TABLE IF NOT EXISTS staking_events (
 id INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE, network TEXT NOT NULL,
 event_type TEXT NOT NULL, block_hash TEXT, height INTEGER, txid TEXT, wallet_name TEXT,
 status TEXT NOT NULL, detected_at TEXT NOT NULL, confirmed_at TEXT, orphaned_at TEXT,
 metadata_json TEXT
);
CREATE TABLE IF NOT EXISTS staking_rewards (
 id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL UNIQUE, network TEXT NOT NULL,
 block_hash TEXT NOT NULL, coinstake_txid TEXT, wallet_name TEXT NOT NULL,
 vout INTEGER,
 wallet_reward_atomic INTEGER, stake_reward_atomic INTEGER, block_reward_atomic INTEGER,
 treasury_reward_atomic INTEGER, gvr_reward_atomic INTEGER, maturity_height INTEGER,
 matured_at TEXT, spent_status TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'UNVERIFIED',
 data_completeness TEXT NOT NULL DEFAULT 'UNKNOWN', source_rpc TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(event_id) REFERENCES staking_events(id)
);
CREATE TABLE IF NOT EXISTS reward_status_history (
 id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, old_status TEXT NOT NULL,
 new_status TEXT NOT NULL, changed_at TEXT NOT NULL, reason TEXT,
 FOREIGN KEY(event_id) REFERENCES staking_events(id)
);
CREATE INDEX IF NOT EXISTS idx_rewards_txid ON staking_rewards(coinstake_txid);
CREATE TABLE IF NOT EXISTS block_validation_events (
 id INTEGER PRIMARY KEY, network TEXT NOT NULL, block_hash TEXT NOT NULL, height INTEGER NOT NULL,
 previous_hash TEXT, event_type TEXT NOT NULL, validation_state TEXT NOT NULL, is_pos INTEGER,
 coinstake_txid TEXT, observed_at TEXT NOT NULL, source TEXT NOT NULL,
 UNIQUE(network, block_hash, event_type)
);
CREATE TABLE IF NOT EXISTS validation_counters (
 network TEXT PRIMARY KEY, observed_blocks INTEGER NOT NULL DEFAULT 0,
 active_chain_blocks INTEGER NOT NULL DEFAULT 0, orphaned_blocks INTEGER NOT NULL DEFAULT 0,
 pos_blocks INTEGER NOT NULL DEFAULT 0, wallet_stake_blocks INTEGER NOT NULL DEFAULT 0,
 reorg_count INTEGER NOT NULL DEFAULT 0, first_observed_at TEXT, last_observed_at TEXT,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reorg_events (
 id INTEGER PRIMARY KEY, network TEXT NOT NULL, detected_at TEXT NOT NULL,
 common_ancestor_height INTEGER, common_ancestor_hash TEXT, old_tip_height INTEGER,
 old_tip_hash TEXT, new_tip_height INTEGER, new_tip_hash TEXT, orphaned_blocks INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL, UNIQUE(network, old_tip_hash, new_tip_hash)
);
CREATE TABLE IF NOT EXISTS collector_runs (
 id INTEGER PRIMARY KEY, collector_name TEXT NOT NULL, started_at TEXT NOT NULL,
 finished_at TEXT, status TEXT NOT NULL, tip_height INTEGER, records_seen INTEGER,
 records_written INTEGER, error_code TEXT, error_message TEXT, owner_pid INTEGER,
 owner_start_ticks INTEGER, owner_boot_id TEXT
);
CREATE TABLE IF NOT EXISTS chain_state (
 network TEXT PRIMARY KEY, tip_height INTEGER, tip_hash TEXT, last_scanned_height INTEGER,
 updated_at TEXT NOT NULL, reorg_epoch INTEGER NOT NULL DEFAULT 0, schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON staking_snapshots(captured_at);
CREATE INDEX IF NOT EXISTS idx_blocks_height ON chain_blocks(network, height);
CREATE INDEX IF NOT EXISTS idx_blocks_hash ON chain_blocks(network, hash);
CREATE INDEX IF NOT EXISTS idx_validation_time ON block_validation_events(observed_at);
CREATE INDEX IF NOT EXISTS idx_events_txid ON staking_events(txid);
CREATE TABLE IF NOT EXISTS reward_inputs (
 id INTEGER PRIMARY KEY, reward_id INTEGER NOT NULL, prev_txid TEXT NOT NULL,
 prev_vout INTEGER NOT NULL, value_atomic INTEGER, ownership_status TEXT NOT NULL,
 source_rpc TEXT NOT NULL, completeness TEXT NOT NULL, UNIQUE(reward_id, prev_txid, prev_vout),
 FOREIGN KEY(reward_id) REFERENCES staking_rewards(id)
);
CREATE TABLE IF NOT EXISTS reward_outputs (
 id INTEGER PRIMARY KEY, reward_id INTEGER NOT NULL, vout INTEGER NOT NULL,
 value_atomic INTEGER, output_class TEXT NOT NULL, ownership_status TEXT NOT NULL,
 source_rpc TEXT NOT NULL, completeness TEXT NOT NULL, UNIQUE(reward_id, vout),
 FOREIGN KEY(reward_id) REFERENCES staking_rewards(id)
);
CREATE TABLE IF NOT EXISTS reward_evidence (
 id INTEGER PRIMARY KEY, reward_id INTEGER NOT NULL, evidence_type TEXT NOT NULL,
 source_rpc TEXT NOT NULL, source_reference TEXT, verified INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, UNIQUE(reward_id, evidence_type, source_rpc, source_reference),
 FOREIGN KEY(reward_id) REFERENCES staking_rewards(id)
);
CREATE INDEX IF NOT EXISTS idx_reward_inputs_reward ON reward_inputs(reward_id);
CREATE INDEX IF NOT EXISTS idx_reward_outputs_reward ON reward_outputs(reward_id);
CREATE INDEX IF NOT EXISTS idx_reward_evidence_reward ON reward_evidence(reward_id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tx_count(block: dict[str, Any]) -> int | None:
    """Return an RPC-provided transaction count, or a complete tx-array count."""
    value = block.get("nTx")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    transactions = block.get("tx")
    if isinstance(transactions, list) and all(isinstance(item, (dict, str)) for item in transactions):
        return len(transactions)
    return None


class IntelligenceDB:
    """Small transactional store; callers must provide already-sanitized RPC data."""

    def __init__(self, path: str | Path, migration_hook: Any = None):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout = 10000")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = NORMAL")
        self.connection.executescript(SCHEMA)
        self._migrate(migration_hook)

    def _migrate(self, migration_hook: Any = None) -> None:
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        if self.path.exists() and self.path.stat().st_size:
            backup = self.path.with_name(self.path.name + f".pre-v{SCHEMA_VERSION}")
            if not backup.exists():
                shutil.copy2(self.path, backup)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            columns = {row[1] for row in self.connection.execute("PRAGMA table_info(staking_rewards)")}
            if "vout" not in columns:
                self.connection.execute("ALTER TABLE staking_rewards ADD COLUMN vout INTEGER")
                if migration_hook:
                    migration_hook("after_vout")
            if "status" not in columns:
                self.connection.execute("ALTER TABLE staking_rewards ADD COLUMN status TEXT NOT NULL DEFAULT 'UNVERIFIED'")
                if migration_hook:
                    migration_hook("after_status")
            if "data_completeness" not in columns:
                self.connection.execute("ALTER TABLE staking_rewards ADD COLUMN data_completeness TEXT NOT NULL DEFAULT 'UNKNOWN'")
                if migration_hook:
                    migration_hook("after_data_completeness")
            run_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(collector_runs)")}
            if "owner_pid" not in run_columns:
                self.connection.execute("ALTER TABLE collector_runs ADD COLUMN owner_pid INTEGER")
            if "owner_start_ticks" not in run_columns:
                self.connection.execute("ALTER TABLE collector_runs ADD COLUMN owner_start_ticks INTEGER")
            if "owner_boot_id" not in run_columns:
                self.connection.execute("ALTER TABLE collector_runs ADD COLUMN owner_boot_id TEXT")
            block_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(chain_blocks)")}
            if "tx_count" not in block_columns:
                self.connection.execute("ALTER TABLE chain_blocks ADD COLUMN tx_count INTEGER")
            self.connection.execute("""CREATE TABLE IF NOT EXISTS reward_status_history (
                id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, old_status TEXT NOT NULL,
                new_status TEXT NOT NULL, changed_at TEXT NOT NULL, reason TEXT,
                FOREIGN KEY(event_id) REFERENCES staking_events(id))""")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_rewards_txid ON staking_rewards(coinstake_txid)")
            self.connection.execute("""CREATE TABLE IF NOT EXISTS reward_inputs (
                id INTEGER PRIMARY KEY, reward_id INTEGER NOT NULL, prev_txid TEXT NOT NULL,
                prev_vout INTEGER NOT NULL, value_atomic INTEGER, ownership_status TEXT NOT NULL,
                source_rpc TEXT NOT NULL, completeness TEXT NOT NULL,
                UNIQUE(reward_id, prev_txid, prev_vout), FOREIGN KEY(reward_id) REFERENCES staking_rewards(id))""")
            self.connection.execute("""CREATE TABLE IF NOT EXISTS reward_outputs (
                id INTEGER PRIMARY KEY, reward_id INTEGER NOT NULL, vout INTEGER NOT NULL,
                value_atomic INTEGER, output_class TEXT NOT NULL, ownership_status TEXT NOT NULL,
                source_rpc TEXT NOT NULL, completeness TEXT NOT NULL,
                UNIQUE(reward_id, vout), FOREIGN KEY(reward_id) REFERENCES staking_rewards(id))""")
            self.connection.execute("""CREATE TABLE IF NOT EXISTS reward_evidence (
                id INTEGER PRIMARY KEY, reward_id INTEGER NOT NULL, evidence_type TEXT NOT NULL,
                source_rpc TEXT NOT NULL, source_reference TEXT, verified INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(reward_id, evidence_type, source_rpc, source_reference),
                FOREIGN KEY(reward_id) REFERENCES staking_rewards(id))""")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_reward_inputs_reward ON reward_inputs(reward_id)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_reward_outputs_reward ON reward_outputs(reward_id)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_reward_evidence_reward ON reward_evidence(reward_id)")
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "IntelligenceDB":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def transaction(self) -> sqlite3.Connection:
        self.connection.execute("BEGIN IMMEDIATE")
        return self.connection

    def start_collector_run(self, collector_name: str, started_at: str | None = None,
                            owner_pid: int | None = None, owner_start_ticks: int | None = None,
                            owner_boot_id: str | None = None) -> int:
        cursor = self.connection.execute(
            """INSERT INTO collector_runs
               (collector_name, started_at, status, owner_pid, owner_start_ticks, owner_boot_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (collector_name, started_at or utc_now(), "RUNNING", owner_pid, owner_start_ticks, owner_boot_id),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def recover_interrupted_runs(self) -> int:
        rows = self.connection.execute(
            "SELECT id, owner_pid, owner_start_ticks, owner_boot_id FROM collector_runs WHERE status='RUNNING'"
        ).fetchall()
        recovered = 0
        for row in rows:
            from ghostnode.intelligence.process_identity import process_identity
            state, ticks, boot_id = process_identity(row["owner_pid"])
            matches = (state == "ACTIVE" and ticks == row["owner_start_ticks"]
                       and boot_id == row["owner_boot_id"])
            has_identity = (isinstance(row["owner_start_ticks"], int)
                            and isinstance(row["owner_boot_id"], str)
                            and bool(row["owner_boot_id"]))
            recoverable = state == "DEAD" or (state == "ACTIVE" and has_identity and not matches)
            if row["owner_boot_id"] and boot_id and boot_id != row["owner_boot_id"]:
                recoverable = True
            if recoverable:
                self.connection.execute(
                    "UPDATE collector_runs SET status='FAILED', finished_at=?, error_code=?, error_message=? WHERE id=?",
                    (utc_now(), "PROCESS_RESTART", "INTERRUPTED_BY_PROCESS_RESTART", row["id"]),
                )
                recovered += 1
        self.connection.commit()
        return recovered

    def finish_collector_run(self, run_id: int, status: str, *, finished_at: str | None = None,
                             tip_height: int | None = None, records_seen: int | None = None,
                             records_written: int | None = None, error_code: str | None = None,
                             error_message: str | None = None) -> None:
        self.connection.execute(
            """UPDATE collector_runs SET finished_at=?, status=?, tip_height=?, records_seen=?,
               records_written=?, error_code=?, error_message=? WHERE id=?""",
            (finished_at or utc_now(), status, tip_height, records_seen, records_written,
             error_code, error_message, run_id),
        )
        self.connection.commit()

    def save_snapshot(self, data: dict[str, Any]) -> None:
        now = data.get("captured_at") or utc_now()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                """INSERT OR IGNORE INTO staking_snapshots
                (captured_at, network, wallet_name, enabled, staking, cause, wallet_weight,
                 network_weight, difficulty, expected_time_seconds, min_stakeable_depth,
                 balance_json, rpc_latency_ms, rpc_status, execution_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (now, data.get("network"), data.get("wallet_name", "ghostmain"),
                 data.get("enabled"), data.get("staking"), data.get("cause"),
                 data.get("wallet_weight"), data.get("network_weight"), data.get("difficulty"),
                 data.get("expected_time_seconds"), data.get("min_stakeable_depth"),
                 json.dumps(data.get("balances"), separators=(",", ":")) if data.get("balances") is not None else None,
                 data.get("rpc_latency_ms"), data.get("rpc_status", "UNKNOWN"), data.get("execution_ms")),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def save_block(self, block: dict[str, Any], network: str, is_pos: bool | None,
                   coinstake_txid: str | None, source: str = "getblock") -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._save_block_in_transaction(block, network, is_pos, coinstake_txid, source,
                                            advance_state=True)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _save_block_in_transaction(self, block: dict[str, Any], network: str,
                                   is_pos: bool | None, coinstake_txid: str | None,
                                   source: str, advance_state: bool) -> None:
        now = utc_now()
        self.connection.execute(
                """INSERT INTO chain_blocks
                (network,height,hash,previous_hash,block_time,confirmations,is_pos,coinstake_txid,tx_count,first_seen_at,last_seen_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(network,hash) DO UPDATE SET last_seen_at=excluded.last_seen_at,
                confirmations=excluded.confirmations,is_active=1,is_pos=excluded.is_pos,
                coinstake_txid=excluded.coinstake_txid,tx_count=excluded.tx_count""",
                (network, block.get("height"), block.get("hash"), block.get("previousblockhash"),
                 block.get("time"), block.get("confirmations"), is_pos, coinstake_txid,
                 _tx_count(block), now, now),
            )
        self.connection.execute(
                """INSERT INTO block_validation_events
                (network,block_hash,height,previous_hash,event_type,validation_state,is_pos,coinstake_txid,observed_at,source)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(network,block_hash,event_type) DO UPDATE SET
                validation_state=excluded.validation_state,is_pos=excluded.is_pos,
                coinstake_txid=excluded.coinstake_txid,observed_at=excluded.observed_at""",
                (network, block.get("hash"), block.get("height"), block.get("previousblockhash"),
                 "block_observed", "OBSERVED", is_pos, coinstake_txid, now, source),
            )
        if advance_state:
            self.connection.execute(
                    """INSERT INTO chain_state(network,tip_height,tip_hash,last_scanned_height,updated_at)
                    VALUES(?,?,?,?,?) ON CONFLICT(network) DO UPDATE SET tip_height=excluded.tip_height,
                    tip_hash=excluded.tip_hash,last_scanned_height=excluded.last_scanned_height,updated_at=excluded.updated_at""",
                    (network, block.get("height"), block.get("hash"), block.get("height"), now),
                )

    def save_block_with_reward(self, block: dict[str, Any], network: str,
                               is_pos: bool | None, coinstake_txid: str | None,
                               reward_writer: Any, source: str = "getblock") -> Any:
        """Atomically persist a block, its reward, and the scanner tip.

        ``reward_writer`` receives this DB while the transaction is open.  It must
        only use the current connection and must not commit or start a transaction.
        """
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._save_block_in_transaction(block, network, is_pos, coinstake_txid, source,
                                            advance_state=False)
            result = reward_writer(self)
            now = utc_now()
            self.connection.execute(
                """INSERT INTO chain_state(network,tip_height,tip_hash,last_scanned_height,updated_at)
                VALUES(?,?,?,?,?) ON CONFLICT(network) DO UPDATE SET tip_height=excluded.tip_height,
                tip_hash=excluded.tip_hash,last_scanned_height=excluded.last_scanned_height,updated_at=excluded.updated_at""",
                (network, block.get("height"), block.get("hash"), block.get("height"), now),
            )
            self.connection.commit()
            return result
        except Exception:
            self.connection.rollback()
            raise

    def save_block_pending(self, block: dict[str, Any], network: str,
                           is_pos: bool | None, coinstake_txid: str | None,
                           source: str = "getblock", in_transaction: bool = False) -> None:
        """Persist observation without advancing the processed-chain cursor."""
        if not in_transaction:
            self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._save_block_in_transaction(block, network, is_pos, coinstake_txid, source,
                                            advance_state=False)
            self.connection.execute(
                "UPDATE block_validation_events SET validation_state='PENDING' "
                "WHERE network=? AND block_hash=? AND event_type='block_observed'",
                (network, block.get("hash")),
            )
            if not in_transaction:
                self.connection.commit()
        except Exception:
            if not in_transaction:
                self.connection.rollback()
            raise

    def state(self, network: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM chain_state WHERE network=?", (network,)).fetchone()

    def mark_orphaned_from(self, network: str, height: int, now: str | None = None,
                           in_transaction: bool = False) -> int:
        now = now or utc_now()
        if not in_transaction:
            self.connection.execute("BEGIN IMMEDIATE")
        try:
            rows = self.connection.execute(
                "SELECT hash FROM chain_blocks WHERE network=? AND height>=? AND is_active=1",
                (network, height),
            ).fetchall()
            self.connection.execute(
                "UPDATE chain_blocks SET is_active=0,last_seen_at=? WHERE network=? AND height>=?",
                (now, network, height),
            )
            hashes = [row[0] for row in rows]
            if hashes:
                placeholders = ",".join("?" for _ in hashes)
                self.connection.execute(
                    f"UPDATE staking_events SET status='ORPHANED',orphaned_at=? WHERE network=? AND block_hash IN ({placeholders})",
                    (now, network, *hashes),
                )
                reward_rows = self.connection.execute(
                    f"SELECT event_id,status FROM staking_rewards WHERE block_hash IN ({','.join('?' for _ in hashes)}) AND status!='ORPHANED'",
                    (*hashes,),
                ).fetchall()
                for reward_row in reward_rows:
                    self.connection.execute(
                        "INSERT INTO reward_status_history(event_id,old_status,new_status,changed_at,reason) VALUES(?,?,?,?,?)",
                        (reward_row["event_id"], reward_row["status"], "ORPHANED", now, "chain reorganization"),
                    )
                self.connection.execute(
                    f"UPDATE staking_rewards SET status='ORPHANED',updated_at=? WHERE block_hash IN ({','.join('?' for _ in hashes)})",
                    (now, *hashes),
                )
            if not in_transaction:
                self.connection.commit()
            return len(hashes)
        except Exception:
            if not in_transaction:
                self.connection.rollback()
            raise

    def record_reorg(self, network: str, old_tip: sqlite3.Row | None, new_tip: dict[str, Any], ancestor: dict[str, Any] | None, orphaned: int,
                     in_transaction: bool = False) -> None:
        now = utc_now()
        if not in_transaction:
            self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                """INSERT OR IGNORE INTO reorg_events
                (network,detected_at,common_ancestor_height,common_ancestor_hash,old_tip_height,old_tip_hash,new_tip_height,new_tip_hash,orphaned_blocks,status)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (network, now, ancestor.get("height") if ancestor else None, ancestor.get("hash") if ancestor else None,
                 old_tip["tip_height"] if old_tip else None, old_tip["tip_hash"] if old_tip else None,
                 new_tip.get("height"), new_tip.get("hash"), orphaned, "DETECTED"),
            )
            if not in_transaction:
                self.connection.commit()
        except Exception:
            if not in_transaction:
                self.connection.rollback()
            raise

    def rebuild_validation_counters(self, network: str) -> sqlite3.Row:
        """Rebuild counters from source tables; counters are never authoritative."""
        now = utc_now()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            observed = self.connection.execute(
                "SELECT count(*) FROM block_validation_events WHERE network=? AND event_type='block_observed'",
                (network,),
            ).fetchone()[0]
            active = self.connection.execute(
                "SELECT count(*) FROM chain_blocks WHERE network=? AND is_active=1", (network,)
            ).fetchone()[0]
            orphaned = self.connection.execute(
                "SELECT count(*) FROM chain_blocks WHERE network=? AND is_active=0", (network,)
            ).fetchone()[0]
            pos = self.connection.execute(
                "SELECT count(*) FROM chain_blocks WHERE network=? AND is_active=1 AND is_pos=1", (network,)
            ).fetchone()[0]
            reorgs = self.connection.execute(
                "SELECT count(*) FROM reorg_events WHERE network=?", (network,)
            ).fetchone()[0]
            self.connection.execute(
                """INSERT INTO validation_counters
                (network,observed_blocks,active_chain_blocks,orphaned_blocks,pos_blocks,reorg_count,updated_at)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(network) DO UPDATE SET
                observed_blocks=excluded.observed_blocks,active_chain_blocks=excluded.active_chain_blocks,
                orphaned_blocks=excluded.orphaned_blocks,pos_blocks=excluded.pos_blocks,
                reorg_count=excluded.reorg_count,updated_at=excluded.updated_at""",
                (network, observed, active, orphaned, pos, reorgs, now),
            )
            self.connection.commit()
            return self.connection.execute("SELECT * FROM validation_counters WHERE network=?", (network,)).fetchone()
        except Exception:
            self.connection.rollback()
            raise

    def __iter__(self) -> Iterator[sqlite3.Row]:
        return iter(self.connection.execute("SELECT * FROM chain_blocks ORDER BY height"))
