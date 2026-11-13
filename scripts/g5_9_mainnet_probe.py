#!/usr/bin/env python3
"""Read-only mainnet sample probe for the G5.8 historical reward engine.

The script never opens SQLite for writing and never runs the collector. It is
intended to be executed from the project's virtualenv in the operator's SSH
session, where ghost-cli can reach the local Ghost Core RPC.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ghostnode.config import Config
from ghostnode.collectors.rpc import _call
from ghostnode.intelligence.collectors import is_pos_transaction
from ghostnode.intelligence.reward_adapter import normalize_reward_transaction
from ghostnode.intelligence.wallet_history import build_verified_history_index


class RateLimitedRPC:
    def __init__(self, config: Config, wallet: str, interval: float = 1.0):
        self.config = config
        self.wallet = wallet
        self.interval = interval
        self.last_call = 0.0
        self.cache: dict[str, tuple[Any, str | None]] = {}
        self.errors = 0
        self.calls = 0

    def __call__(self, method: str, args: list[Any] | None = None):
        key = json.dumps([method, args], sort_keys=True, separators=(",", ":"))
        if key in self.cache:
            return self.cache[key]
        delay = self.interval - (time.monotonic() - self.last_call)
        if delay > 0:
            time.sleep(delay)
        wallet = self.wallet if method in {"listtransactions", "getaddressinfo", "gettransaction"} else None
        result = _call(method, self.config, wallet=wallet, args=args)
        self.last_call = time.monotonic()
        self.calls += 1
        if result[1] is not None:
            self.errors += 1
        self.cache[key] = result
        return result


def _read_blocks(path: Path, limit: int) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT height, hash FROM chain_blocks "
            "WHERE network='main' AND is_active=1 AND is_pos=1 "
            "ORDER BY height DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _wallet_history(rpc: RateLimitedRPC) -> tuple[list[dict[str, Any]] | None, str]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for page in range(20):
        batch, error = rpc("listtransactions", ["*", 1000, page * 1000])
        if error or not isinstance(batch, list):
            return None, "RPC_ERROR"
        for item in batch:
            if isinstance(item, dict):
                key = (item.get("txid"), item.get("vout"), item.get("blockhash"))
                if key not in seen:
                    seen.add(key)
                    entries.append(item)
        if len(batch) < 1000:
            return entries, "COMPLETE"
    return entries, "LIMIT_REACHED"


def _output_view(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"valid": False}
    script = item.get("scriptPubKey")
    return {
        "n": item.get("n"),
        "value_present": "value" in item,
        "scriptPubKey_present": isinstance(script, dict),
        "script_type": script.get("type") if isinstance(script, dict) else None,
        "ownership": None,
        "output_class": item.get("output_class", "unknown"),
    }


def _result_view(block: dict[str, Any], normalized: Any, expected_hash: str) -> dict[str, Any]:
    txs = block.get("tx") if isinstance(block, dict) else []
    tx = txs[0] if isinstance(txs, list) and txs and isinstance(txs[0], dict) else {}
    inputs = []
    for item in normalized.inputs:
        inputs.append({"vout": item.prev_vout, "resolution": item.confidence.value,
                       "value_present": item.value_atomic is not None,
                       "ownership": item.ownership_status.value,
                       "source": item.evidence_source})
    return {
        "height": block.get("height"),
        "blockhash": block.get("hash"),
        "blockhash_matches_expected": block.get("hash") == expected_hash,
        "coinstake_txid": tx.get("txid"),
        "inputs": inputs,
        "outputs": [_output_view(item) for item in tx.get("vout", [])],
        "prevout_resolution": {"total": len(inputs),
                               "verified": sum(i["resolution"] == "VERIFIED" for i in inputs),
                               "partial": sum(i["resolution"] == "PARTIAL" for i in inputs),
                               "unknown": sum(i["resolution"] == "UNKNOWN" for i in inputs)},
        "ownership_status": [item.ownership_status.value for item in normalized.outputs],
        "principal_atomic": normalized.attribution.principal_return_atomic,
        "reward_atomic": normalized.attribution.wallet_reward_atomic,
        "completeness": normalized.status.value,
        "errors": [],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    db_path = Path(args.db).expanduser()
    rows = _read_blocks(db_path, min(args.limit, 10))
    rpc = RateLimitedRPC(Config(cli_path=args.cli, datadir=args.datadir, timeout=args.timeout), args.wallet)
    started = time.monotonic()
    history, history_status = _wallet_history(rpc)
    index = build_verified_history_index(history, rpc, {})
    results = []
    for row in rows:
        expected_hash, error = rpc("getblockhash", [row["height"]])
        if error or expected_hash != row["hash"]:
            results.append({"height": row["height"], "blockhash": row["hash"],
                            "completeness": "UNKNOWN", "errors": [error or "chain mismatch"]})
            continue
        block, error = rpc("getblock", [expected_hash, 2, True])
        if error or not isinstance(block, dict):
            results.append({"height": row["height"], "blockhash": expected_hash,
                            "completeness": "UNKNOWN", "errors": [error or "invalid block"]})
            continue
        if block.get("height") != row["height"] or block.get("hash") != expected_hash:
            results.append({"height": row["height"], "blockhash": expected_hash,
                            "completeness": "UNKNOWN", "errors": ["block identity mismatch"]})
            continue
        txs = block.get("tx")
        tx = txs[0] if isinstance(txs, list) and txs else None
        if not is_pos_transaction(tx):
            results.append({"height": row["height"], "blockhash": expected_hash,
                            "completeness": "UNKNOWN", "errors": ["stored PoS row is not PoS in RPC block"]})
            continue
        normalized = normalize_reward_transaction(block, rpc, index)
        results.append(_result_view(block, normalized, expected_hash))
    return {"schema": "g5.9-mainnet-validation-v1", "read_only": True,
            "blocks_requested": len(rows), "history_status": history_status,
            "verified_history_entries": len(index), "rpc_calls": rpc.calls,
            "rpc_errors": rpc.errors, "elapsed_seconds": round(time.monotonic() - started, 3),
            "blocks": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/staking_intelligence.sqlite3")
    parser.add_argument("--cli", default=None, help="ghost-cli path; defaults to GHOSTNODE_CLI_PATH or PATH")
    parser.add_argument("--datadir", default=None, help="Ghost datadir; defaults to GHOSTNODE_DATADIR or ~/.ghost")
    parser.add_argument("--wallet", default="ghostmain")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", default="g5_9_mainnet_validation.json")
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error("--limit must be between 1 and 10")
    report = run(args)
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"report={output} blocks={report['blocks_requested']} rpc_calls={report['rpc_calls']} errors={report['rpc_errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
