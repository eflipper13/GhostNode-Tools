from __future__ import annotations

import time
import sqlite3
import re
from dataclasses import dataclass
from pathlib import Path
from contextlib import nullcontext
from typing import Any, Callable

from ghostnode.intelligence.db import IntelligenceDB, utc_now
from ghostnode.intelligence.lock import CollectorLock, InstanceLock
from ghostnode.intelligence.rewards import (_track_reward_in_transaction, maturity_depth_from_core,
                                             refresh_reward_lifecycle)
from ghostnode.intelligence.reward_adapter import normalize_reward_transaction
from ghostnode.intelligence.wallet_history import build_verified_history_index


RPC = Callable[[str, list[Any] | None], tuple[Any, str | None]]
TRANSACTION_PAGE_SIZE = 1000
MAX_TRANSACTION_PAGES = 20


def is_pos_transaction(transaction: Any) -> bool:
    """Detect Ghost PoS transactions from explicit RPC markers or script opcode."""
    if not isinstance(transaction, dict):
        return False
    if transaction.get("coinstakeinfo") is not None or transaction.get("is_coinstake") is True:
        return True
    for output in transaction.get("vout", []):
        script = output.get("scriptPubKey") if isinstance(output, dict) else None
        if not isinstance(script, dict):
            continue
        asm = script.get("asm")
        if isinstance(asm, str) and re.search(r"(?:^|\s)OP_ISCOINSTAKE(?:$|\s)", asm):
            return True
    return False


class StalePlan(RuntimeError):
    """The read-only RPC plan no longer matches the writer database state."""


@dataclass(frozen=True)
class BlockScanPlan:
    network: str
    target_height: int
    expected_state: tuple[Any, ...] | None
    blocks: tuple[dict[str, Any], ...]
    rewards: tuple[tuple[dict[str, Any], list[dict[str, Any]] | None, str], ...]
    baseline: bool = False
    ancestor: dict[str, Any] | None = None
    old_state: Any = None
    baseline_hash: str | None = None
    plan_status: str | None = None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def collect_snapshot(db: IntelligenceDB, rpc: RPC, wallet_name: str = "ghostmain", lock_path: str | None = None) -> dict[str, Any]:
    if lock_path == "":
        return _collect_snapshot(db, rpc, wallet_name)
    instance = InstanceLock(str(db.path) + ".lock.instance")
    writer = CollectorLock(lock_path or str(db.path) + ".lock", blocking=True)
    with instance:
        with writer:
            return _collect_snapshot(db, rpc, wallet_name)


def _collect_snapshot(db: IntelligenceDB, rpc: RPC, wallet_name: str) -> dict[str, Any]:
    started = time.monotonic()
    chain, chain_error = rpc("getblockchaininfo", None)
    stake, stake_error = rpc("getstakinginfo", [wallet_name])
    balances, balances_error = rpc("getbalances", [wallet_name])
    data: dict[str, Any] = {
        "captured_at": utc_now(), "wallet_name": wallet_name,
        "network": chain.get("chain") if isinstance(chain, dict) else None,
        "enabled": stake.get("enabled") if isinstance(stake, dict) else None,
        "staking": stake.get("staking") if isinstance(stake, dict) else None,
        "cause": stake.get("cause") if isinstance(stake, dict) else None,
        "wallet_weight": _number(stake.get("weight")) if isinstance(stake, dict) else None,
        "network_weight": _number(stake.get("netstakeweight")) if isinstance(stake, dict) else None,
        "difficulty": _number(stake.get("difficulty")) if isinstance(stake, dict) else None,
        "expected_time_seconds": _number(stake.get("expectedtime")) if isinstance(stake, dict) else None,
        "min_stakeable_depth": _number(stake.get("minstakeabledepth")) if isinstance(stake, dict) else None,
        "balances": balances if isinstance(balances, dict) else None,
        "rpc_latency_ms": None,
        "rpc_status": "OK" if not any((chain_error, stake_error, balances_error)) else "UNKNOWN",
        "execution_ms": round((time.monotonic() - started) * 1000, 2),
    }
    db.save_snapshot(data)
    return data


def prepare_snapshot(rpc: RPC, wallet_name: str = "ghostmain") -> dict[str, Any]:
    """Collect snapshot data without opening or writing SQLite."""
    started = time.monotonic()
    chain, chain_error = rpc("getblockchaininfo", None)
    stake, stake_error = rpc("getstakinginfo", [wallet_name])
    balances, balances_error = rpc("getbalances", [wallet_name])
    return {
        "captured_at": utc_now(), "wallet_name": wallet_name,
        "network": chain.get("chain") if isinstance(chain, dict) else None,
        "enabled": stake.get("enabled") if isinstance(stake, dict) else None,
        "staking": stake.get("staking") if isinstance(stake, dict) else None,
        "cause": stake.get("cause") if isinstance(stake, dict) else None,
        "wallet_weight": _number(stake.get("weight")) if isinstance(stake, dict) else None,
        "network_weight": _number(stake.get("netstakeweight")) if isinstance(stake, dict) else None,
        "difficulty": _number(stake.get("difficulty")) if isinstance(stake, dict) else None,
        "expected_time_seconds": _number(stake.get("expectedtime")) if isinstance(stake, dict) else None,
        "min_stakeable_depth": _number(stake.get("minstakeabledepth")) if isinstance(stake, dict) else None,
        "balances": balances if isinstance(balances, dict) else None,
        "rpc_latency_ms": None,
        "rpc_status": "OK" if not any((chain_error, stake_error, balances_error)) else "UNKNOWN",
        "execution_ms": round((time.monotonic() - started) * 1000, 2),
    }


def save_snapshot_plan(db: IntelligenceDB, data: dict[str, Any]) -> None:
    db.save_snapshot(data)


def _read_state(path: str | Path, network: str) -> Any:
    target = Path(path).expanduser()
    if not target.exists():
        return None
    connection = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute("SELECT * FROM chain_state WHERE network=?", (network,)).fetchone()
    finally:
        connection.close()


def prepare_block_plan(path: str | Path, rpc: RPC, network: str = "main", batch_size: int = 100,
                       wallet_name: str = "ghostmain", maturity_depth: int | None = None) -> BlockScanPlan:
    """Perform all RPC and DB reads before acquiring the writer lock."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    chain, error = rpc("getblockchaininfo", None)
    if error or not isinstance(chain, dict) or not isinstance(chain.get("blocks"), int):
        raise RuntimeError("RPC blockchain preflight failed")
    target = chain["blocks"]
    state = _read_state(path, network)
    expected = tuple(state[key] for key in ("tip_height", "tip_hash", "last_scanned_height")) if state else None
    if state is None:
        return BlockScanPlan(network, target, None, (), (), baseline=True,
                             baseline_hash=chain.get("bestblockhash"))
    start = int(state["last_scanned_height"]) + 1
    if start > target:
        return BlockScanPlan(network, target, expected, (), ())
    ancestor = None
    first = _get_block(rpc, start)
    if first is None:
        raise RuntimeError(f"unable to read block {start}")
    if state["tip_hash"] and first.get("previousblockhash") != state["tip_hash"]:
        class ReadDB:
            connection = sqlite3.connect(f"file:{Path(path).expanduser()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
        try:
            ancestor = _find_common_ancestor(ReadDB(), rpc, network, start - 1, target)
        finally:
            ReadDB.connection.close()
        if ancestor is None:
            raise RuntimeError("unable to find common ancestor")
        start = ancestor["height"] + 1
    blocks: list[dict[str, Any]] = []
    rewards: list[tuple[dict[str, Any], list[dict[str, Any]] | None, str]] = []
    previous = ancestor["hash"] if ancestor else state["tip_hash"]
    end = min(target, start + batch_size - 1)
    plan_status = None

    # Cache wallet history once per prepared block plan.
    wallet_history_loaded = False
    wallet_entries_cache = None
    wallet_history_status = "NOT_LOADED"
    verified_history_index: dict[str, str] = {}
    blockhash_cache: dict[int, str] = {}

    for height in range(start, end + 1):
        block = _get_block(rpc, height)
        if block is None or (previous and block.get("previousblockhash") != previous):
            if blocks:
                plan_status = "RPC_ERROR"
                break
            raise RuntimeError("chain changed while preparing block plan")
        blocks.append(block)
        txs = block.get("tx")
        first_tx = txs[0] if isinstance(txs, list) and txs else None
        is_pos = is_pos_transaction(first_tx)
        if is_pos and first_tx.get("txid"):
            reward, _ = rpc("getblockreward", [height])
            if not wallet_history_loaded:
                wallet_entries_cache, wallet_history_status = _list_wallet_transactions(rpc)
                verified_history_index = build_verified_history_index(
                    wallet_entries_cache, rpc, blockhash_cache)
                wallet_history_loaded = True

            entries = wallet_entries_cache
            history_status = wallet_history_status

            reward_block = dict(reward) if isinstance(reward, dict) else {}
            reward_block.update({"hash": block.get("hash"), "height": height, "coinstake": first_tx["txid"]})
            try:
                normalized = normalize_reward_transaction(block, rpc, verified_history_index)
                if normalized.inputs or normalized.outputs:
                    reward_block.update(normalized.as_v2_fields())
            except (AssertionError, TypeError, ValueError):
                # A caller may expose only the legacy read-only RPC subset;
                # retain the legacy path rather than inventing V2 data.
                pass
            rewards.append((reward_block, entries, history_status))
        else:
            rewards.append(({}, [], "COMPLETE"))
        previous = block.get("hash")
    return BlockScanPlan(network, target, expected, tuple(blocks), tuple(rewards), False, ancestor, state,
                         None, plan_status)


def apply_block_plan(db: IntelligenceDB, plan: BlockScanPlan, wallet_name: str = "ghostmain",
                     maturity_depth: int | None = None,
                     validated_tip_hash: str | None = None) -> dict[str, Any]:
    """Revalidate and apply a previously prepared plan under the writer lock."""
    state = db.state(plan.network)
    current = tuple(state[key] for key in ("tip_height", "tip_hash", "last_scanned_height")) if state else None
    if current != plan.expected_state:
        raise StalePlan("chain_state changed before write")
    if plan.blocks and validated_tip_hash != plan.blocks[-1].get("hash"):
        raise StalePlan("prepared tip hash is stale")
    if plan.baseline:
        now = utc_now()
        db.connection.execute("BEGIN IMMEDIATE")
        try:
            db.connection.execute("INSERT INTO chain_state(network,tip_height,tip_hash,last_scanned_height,updated_at) VALUES(?,?,?,?,?)",
                                 (plan.network, plan.target_height, plan.baseline_hash,
                                  plan.target_height, now))
            db.connection.execute(
                "INSERT OR IGNORE INTO block_validation_events "
                "(network,block_hash,height,event_type,validation_state,observed_at,source) "
                "VALUES(?,?,?,?,?,?,?)",
                (plan.network, plan.baseline_hash or f"baseline:{plan.target_height}",
                 plan.target_height, "baseline", "BASELINE", now, "getblockchaininfo"),
            )
            db.connection.commit()
        except Exception:
            db.connection.rollback()
            raise
        return {"status": "OK", "processed": 0, "height": plan.target_height, "baseline": True}
    atomic_reorg = plan.ancestor is not None
    if atomic_reorg:
        db.connection.execute("BEGIN IMMEDIATE")
    incomplete_status = None
    processed = 0
    try:
        if plan.ancestor:
            orphaned = db.mark_orphaned_from(plan.network, plan.ancestor["height"] + 1,
                                             in_transaction=True)
            db.record_reorg(plan.network, plan.old_state,
                            {"height": plan.target_height, "hash": None}, plan.ancestor,
                            orphaned, in_transaction=True)
        for block, (reward_block, entries, history_status) in zip(plan.blocks, plan.rewards):
            txs = block.get("tx")
            first = txs[0] if isinstance(txs, list) and txs else None
            is_pos = is_pos_transaction(first)
            coinstake = first.get("txid") if is_pos and isinstance(first, dict) else None
            incomplete = is_pos and coinstake and history_status != "COMPLETE"
            if incomplete:
                incomplete_status = history_status
            if atomic_reorg:
                db._save_block_in_transaction(block, plan.network, is_pos, coinstake,
                                               "getblock", advance_state=not incomplete)
                if is_pos and coinstake and history_status == "COMPLETE":
                    _track_reward_in_transaction(db, reward_block, entries or [], wallet_name,
                                                 maturity_depth or maturity_depth_from_core())
                elif is_pos and coinstake:
                    db.connection.execute(
                        "UPDATE block_validation_events SET validation_state='PENDING' "
                        "WHERE network=? AND block_hash=? AND event_type='block_observed'",
                        (plan.network, block.get("hash")),
                    )
            elif is_pos and coinstake and history_status == "COMPLETE":
                db.save_block_with_reward(block, plan.network, is_pos, coinstake,
                                          lambda txdb, rb=reward_block, es=entries: _track_reward_in_transaction(
                                              txdb, rb, es or [], wallet_name,
                                              maturity_depth or maturity_depth_from_core()))
            elif is_pos and coinstake:
                db.save_block_pending(block, plan.network, is_pos, coinstake)
            else:
                db.save_block(block, plan.network, is_pos, coinstake)
            processed += 1
            if incomplete:
                break
        if atomic_reorg:
            db.connection.commit()
    except Exception:
        if atomic_reorg:
            db.connection.rollback()
        raise
    refresh_reward_lifecycle(db, plan.target_height, maturity_depth or maturity_depth_from_core())
    if incomplete_status or plan.plan_status:
        return {"status": "UNKNOWN", "processed": processed,
                "history_status": incomplete_status or plan.plan_status,
                "height": plan.target_height}
    return {"status": "OK", "processed": processed, "height": plan.target_height,
            "complete": not plan.blocks or plan.blocks[-1].get("height") >= plan.target_height}


def scan_block(db: IntelligenceDB, rpc: RPC, network: str = "main") -> dict[str, Any] | None:
    chain, error = rpc("getblockchaininfo", None)
    if error or not isinstance(chain, dict) or not isinstance(chain.get("blocks"), int):
        return None
    height = chain["blocks"]
    block_hash, error = rpc("getblockhash", [height])
    if error or not isinstance(block_hash, str):
        return None
    block, error = rpc("getblock", [block_hash, 2, True])
    if error or not isinstance(block, dict):
        return None
    txs = block.get("tx")
    first = txs[0] if isinstance(txs, list) and txs else None
    is_pos = None
    coinstake = None
    if isinstance(first, dict):
        is_pos = is_pos_transaction(first)
        coinstake = first.get("txid") if is_pos else None
    db.save_block(block, network, is_pos, coinstake)
    return {"height": height, "hash": block_hash, "is_pos": is_pos, "coinstake_txid": coinstake}


def _get_block(rpc: RPC, height: int) -> dict[str, Any] | None:
    block_hash, error = rpc("getblockhash", [height])
    if error or not isinstance(block_hash, str):
        return None
    block, error = rpc("getblock", [block_hash, 2, True])
    if error or not isinstance(block, dict) or block.get("hash") != block_hash:
        return None
    return block


def _list_wallet_transactions(rpc: RPC) -> tuple[list[dict[str, Any]] | None, str]:
    """Read a bounded history window and return COMPLETE/RPC_ERROR/LIMIT_REACHED."""
    entries: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for page in range(MAX_TRANSACTION_PAGES):
        batch, error = rpc("listtransactions", ["*", TRANSACTION_PAGE_SIZE,
                                                  page * TRANSACTION_PAGE_SIZE])
        if error:
            return None, "RPC_ERROR"
        if not isinstance(batch, list):
            return None, "RPC_ERROR"
        for entry in batch:
            if not isinstance(entry, dict):
                continue
            key = (entry.get("txid"), entry.get("vout"), entry.get("blockhash"))
            if key not in seen:
                seen.add(key)
                entries.append(entry)
        if len(batch) < TRANSACTION_PAGE_SIZE:
            return entries, "COMPLETE"
    return entries, "LIMIT_REACHED"


def _find_common_ancestor(db: IntelligenceDB, rpc: RPC, network: str, start_height: int, target_height: int) -> dict[str, Any] | None:
    """Walk backwards through stored heights until the active RPC chain agrees."""
    for height in range(min(start_height, target_height), -1, -1):
        row = db.connection.execute(
            "SELECT hash FROM chain_blocks WHERE network=? AND height=? AND is_active=1 ORDER BY id DESC LIMIT 1",
            (network, height),
        ).fetchone()
        if not row:
            continue
        active_hash, error = rpc("getblockhash", [height])
        if not error and active_hash == row["hash"]:
            return {"height": height, "hash": active_hash}
    return None


def scan_catch_up(db: IntelligenceDB, rpc: RPC, network: str = "main", batch_size: int = 100,
                  lock_path: str | None = None, wallet_name: str = "ghostmain",
                  maturity_depth: int | None = None, external_lock: bool = False) -> dict[str, Any]:
    """Compatibility wrapper using the phase-separated planner and writer."""
    instance = nullcontext() if external_lock else InstanceLock(str(db.path) + ".lock.instance")
    with instance:
        try:
            plan = prepare_block_plan(db.path, rpc, network, batch_size, wallet_name, maturity_depth)
        except RuntimeError as exc:
            return {"status": "UNKNOWN", "processed": 0, "error": str(exc)}
        lock = nullcontext() if external_lock else CollectorLock(lock_path or str(db.path) + ".lock", blocking=True)
        with lock:
            validated_tip_hash = None
            if plan.blocks:
                validated_tip_hash, error = rpc("getblockhash", [plan.blocks[-1].get("height")])
                if error or not isinstance(validated_tip_hash, str):
                    return {"status": "STALE", "processed": 0, "error": "tip hash revalidation failed"}
            try:
                return apply_block_plan(db, plan, wallet_name, maturity_depth, validated_tip_hash)
            except StalePlan as exc:
                return {"status": "STALE", "processed": 0, "error": str(exc)}
