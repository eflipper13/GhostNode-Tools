#!/usr/bin/env python3
"""Read-only wallet-specific staking discovery probe."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from ghostnode.config import Config
from ghostnode.collectors.rpc import _call
from ghostnode.intelligence.collectors import is_pos_transaction
from ghostnode.intelligence.reward_adapter import normalize_reward_transaction
from ghostnode.intelligence.wallet_history import build_verified_history_index


class RPC:
    def __init__(self, config: Config, wallet: str, interval: float = 1.0):
        self.config, self.wallet, self.interval = config, wallet, interval
        self.last = 0.0
        self.cache: dict[str, tuple[Any, str | None]] = {}
        self.calls = 0
        self.errors = 0

    def __call__(self, method: str, args: list[Any] | None = None):
        key = json.dumps([method, args], sort_keys=True)
        if key in self.cache:
            return self.cache[key]
        wait = self.interval - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        wallet = self.wallet if method in {"getwalletinfo", "getstakinginfo", "getbalances",
                                           "listtransactions", "listunspent", "gettransaction",
                                           "getaddressinfo"} else None
        result = _call(method, self.config, wallet=wallet, args=args)
        self.last = time.monotonic()
        self.calls += 1
        self.errors += int(result[1] is not None)
        self.cache[key] = result
        return result


def _shape(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()
                if key not in {"address", "addresses", "stakeaddresses", "txid", "hash", "hex", "scriptPubKey"}}
    if isinstance(value, list):
        return {"count": len(value), "item_types": sorted({type(item).__name__ for item in value})}
    if isinstance(value, (int, float, bool, str)):
        return type(value).__name__
    return type(value).__name__


def _utxo_view(items: Any) -> dict[str, Any]:
    if not isinstance(items, list):
        return {"count": 0, "status": "UNKNOWN"}
    return {"count": len(items),
            "stakeable_true": sum(item.get("stakeable") is True for item in items if isinstance(item, dict)),
            "spendable_true": sum(item.get("spendable") is True for item in items if isinstance(item, dict)),
            "items": [{"txid_present": isinstance(item.get("txid"), str),
                        "vout": item.get("vout"),
                        "confirmations": item.get("confirmations"),
                        "amount_present": "amount" in item,
                        "stakeable": item.get("stakeable") if isinstance(item.get("stakeable"), bool) else "UNKNOWN",
                        "spendable": item.get("spendable") if isinstance(item.get("spendable"), bool) else "UNKNOWN"}
                       for item in items if isinstance(item, dict)]}


def _history(rpc: RPC) -> tuple[list[dict[str, Any]] | None, str]:
    entries: list[dict[str, Any]] = []
    seen = set()
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


def run(args: argparse.Namespace) -> dict[str, Any]:
    rpc = RPC(Config(cli_path=args.cli, datadir=args.datadir, timeout=args.timeout), args.wallet)
    wallet_data = {}
    unspent = None
    for method, call_args in (("getwalletinfo", None), ("getstakinginfo", None),
                              ("getbalances", None), ("listunspent", [0, 9999999])):
        value, error = rpc(method, call_args)
        if method == "listunspent":
            unspent = value
        wallet_data[method] = {"status": "ERROR" if error else "SUCCESS",
                               "shape": _utxo_view(value) if method == "listunspent" else _shape(value), "error": error}
    history, history_status = _history(rpc)
    categories = Counter(item.get("category", "UNKNOWN") for item in history or [] if isinstance(item, dict))
    index = build_verified_history_index(history, rpc, {})
    receive_entries = [item for item in history or []
                       if isinstance(item, dict) and item.get("category") == "receive"][:4]
    receive_details = []
    for item in receive_entries:
        tx, error = rpc("gettransaction", [item.get("txid")])
        receive_details.append({"status": "ERROR" if error else "SUCCESS",
                                "shape": _shape(tx), "error": error,
                                "blockhash_present": isinstance(item.get("blockhash"), str),
                                "height_present": isinstance(item.get("blockheight"), int)})
    candidates = []
    for item in history or []:
        if not isinstance(item, dict) or item.get("category") not in {"stake", "generate", "immature", "orphan", "orphaned_stake"}:
            continue
        txid = item.get("txid")
        blockhash = item.get("blockhash")
        if not isinstance(txid, str) or not isinstance(blockhash, str):
            continue
        block, error = rpc("getrawtransaction", [txid, 1, blockhash])
        if error or not isinstance(block, dict):
            candidates.append({"status": "UNKNOWN", "reason": "transaction unavailable"})
            continue
        pos = is_pos_transaction(block)
        normalized = normalize_reward_transaction({"hash": blockhash, "height": item.get("blockheight"), "tx": [block]}, rpc, index)
        candidates.append({"status": normalized.status.value if pos else "NOT_POS",
                          "pos_detected": pos, "ownership": sorted({x.ownership_status.value for x in normalized.outputs}),
                          "completeness": normalized.status.value,
                          "reward_confirmed": normalized.attribution.wallet_reward_atomic is not None and normalized.attribution.completeness.value == "COMPLETE"})
    return {"status": "OK", "wallet": args.wallet, "wallet_data": wallet_data,
            "history_status": history_status, "history_count": len(history or []),
            "categories": dict(sorted(categories.items())), "verified_history_entries": len(index),
            "receive_transaction_details": receive_details,
            "staking_candidates": candidates, "rpc_calls": rpc.calls, "rpc_errors": rpc.errors,
            "utxo_summary": _utxo_view(unspent),
            "conclusion": {"wallet_staking_events": "UNKNOWN", "ownership": "UNKNOWN",
                           "g5_8_accounting": "UNKNOWN"}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", default=None, help="ghost-cli path; defaults to GHOSTNODE_CLI_PATH or PATH")
    parser.add_argument("--datadir", default=None, help="Ghost datadir; defaults to GHOSTNODE_DATADIR or ~/.ghost")
    parser.add_argument("--wallet", default="ghostmain")
    parser.add_argument("--db", default="data/staking_intelligence.sqlite3")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", default="g5_9_wallet_audit.json")
    args = parser.parse_args()
    report = run(args)
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"report={args.output} history={report['history_count']} candidates={len(report['staking_candidates'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
