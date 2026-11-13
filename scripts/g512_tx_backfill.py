#!/usr/bin/env python3
"""Bounded, resumable transaction-count backfill.

Default mode is read-only and reports candidates. ``--apply`` is an explicit
write operation and is never invoked by the collector.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

from ghostnode.collectors.rpc import _call
from ghostnode.config import Config
from ghostnode.intelligence.db import IntelligenceDB


def _count(block: Any) -> int | None:
    if not isinstance(block, dict):
        return None
    value = block.get("nTx")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    tx = block.get("tx")
    if isinstance(tx, list) and all(isinstance(item, (dict, str)) for item in tx):
        return len(tx)
    return None


def _rows(path: Path, limit: int) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(
            "SELECT id,height,hash FROM chain_blocks "
            "WHERE tx_count IS NULL AND is_active=1 ORDER BY height LIMIT ?", (limit,)
        ).fetchall()]
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/staking_intelligence.sqlite3")
    parser.add_argument("--cli", default=None)
    parser.add_argument("--datadir", default=None)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--apply", action="store_true", help="write resolved NULL tx_count values")
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 100:
        parser.error("--limit must be between 1 and 100")
    defaults = Config()
    config = Config(cli_path=args.cli or defaults.cli_path, datadir=args.datadir or defaults.datadir)
    candidates = _rows(Path(args.db).expanduser(), args.limit)
    updates: list[tuple[int, int]] = []
    for row in candidates:
        block, error = _call("getblock", config, args=[row["hash"], 1, True])
        count = _count(block) if error is None else None
        print(f"height={row['height']} tx_count={count if count is not None else 'UNKNOWN'}")
        if count is not None:
            updates.append((count, row["id"]))
    if args.apply and updates:
        with IntelligenceDB(args.db) as db:
            db.connection.execute("BEGIN IMMEDIATE")
            try:
                db.connection.executemany("UPDATE chain_blocks SET tx_count=? WHERE id=? AND tx_count IS NULL", updates)
                db.connection.commit()
            except Exception:
                db.connection.rollback()
                raise
    print(f"candidates={len(candidates)} resolved={len(updates)} applied={len(updates) if args.apply else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
