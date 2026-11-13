from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from ghostnode.intelligence.db import IntelligenceDB, utc_now

COINBASE_MATURITY = 100
MAX_ATOMIC = 9_223_372_036_854_775_807

class RewardStatus(StrEnum):
    DETECTED = "DETECTED"
    IDENTIFIED = "IDENTIFIED"
    IMMATURE = "IMMATURE"
    MATURED = "MATURED"
    SPENT = "SPENT"
    ORPHANED = "ORPHANED"
    UNVERIFIED = "UNVERIFIED"


class DataCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RewardAttribution:
    input_value_atomic: int | None
    principal_return_atomic: int | None
    wallet_reward_atomic: int | None
    other_outputs_atomic: int | None
    completeness: DataCompleteness
    ownership_verified: bool


def attribute_reward(inputs: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> RewardAttribution:
    """Conservatively attribute wallet reward from confirmed inputs/outputs."""
    if not isinstance(inputs, list) or not isinstance(outputs, list) or not inputs or not outputs:
        return RewardAttribution(None, None, None, None, DataCompleteness.UNKNOWN, False)
    if any(not isinstance(item, dict) for item in inputs + outputs):
        return RewardAttribution(None, None, None, None, DataCompleteness.PARTIAL, False)
    input_values = [_atomic(item.get("value_atomic", item.get("value"))) for item in inputs]
    if any(value is None for value in input_values):
        return RewardAttribution(None, None, None, None, DataCompleteness.PARTIAL, False)
    prevouts = [(item.get("prev_txid"), item.get("prev_vout")) for item in inputs]
    if any(txid is None or not isinstance(vout, int) or isinstance(vout, bool) for txid, vout in prevouts):
        return RewardAttribution(sum(input_values), None, None, None, DataCompleteness.PARTIAL, False)
    if len(set(prevouts)) != len(prevouts):
        return RewardAttribution(sum(input_values), None, None, None, DataCompleteness.PARTIAL, False)
    vouts = [item.get("vout") for item in outputs]
    if any(not isinstance(vout, int) or isinstance(vout, bool) for vout in vouts) or len(set(vouts)) != len(vouts):
        return RewardAttribution(sum(input_values), None, None, None, DataCompleteness.PARTIAL, False)
    allowed = {"principal", "wallet_reward", "unknown"}
    if any(item.get("output_class") not in allowed for item in outputs):
        return RewardAttribution(sum(input_values), None, None, None, DataCompleteness.PARTIAL, False)
    values = [_atomic(item.get("value_atomic", item.get("value"))) for item in outputs]
    if any(value is None for value in values):
        return RewardAttribution(sum(input_values), None, None, None, DataCompleteness.PARTIAL, False)
    if any(item.get("output_class") == "unknown" for item in outputs):
        return RewardAttribution(sum(input_values), None, None, None, DataCompleteness.PARTIAL, False)
    if any(item.get("output_class") in {"principal", "wallet_reward"} and item.get("owner_verified") is not True
           for item in outputs):
        return RewardAttribution(sum(input_values), None, None, None, DataCompleteness.PARTIAL, False)
    wallet_outputs = [item for item in outputs if isinstance(item, dict) and item.get("owner_verified") is True]
    if not wallet_outputs or any(_atomic(item.get("value_atomic", item.get("value"))) is None for item in wallet_outputs):
        return RewardAttribution(sum(input_values), None, None, None, DataCompleteness.PARTIAL, False)
    total_wallet = sum(_atomic(item.get("value_atomic", item.get("value"))) for item in wallet_outputs)
    principal = sum(_atomic(item.get("value_atomic", item.get("value"))) for item in wallet_outputs
                    if item.get("output_class") == "principal")
    reward = total_wallet - principal
    other = sum((_atomic(item.get("value_atomic", item.get("value"))) or 0) for item in outputs
                if item not in wallet_outputs and _atomic(item.get("value_atomic", item.get("value"))) is not None)
    return RewardAttribution(sum(input_values), principal, reward, other, DataCompleteness.COMPLETE, True)


@dataclass(frozen=True)
class RewardMatch:
    block_hash: str
    block_height: int | None
    txid: str
    vout: int
    wallet_reward_atomic: int
    status: RewardStatus
    owner_verified: bool
    source: str
    completeness: DataCompleteness


def _atomic(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        amount = int(Decimal(str(value)) * Decimal(100_000_000))
        return amount if 0 <= amount <= MAX_ATOMIC else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _status(entry: dict[str, Any], maturity_depth: int | None) -> RewardStatus:
    if entry.get("orphaned") is True or entry.get("category") == "orphaned_stake":
        return RewardStatus.ORPHANED
    if entry.get("spent") is True:
        return RewardStatus.SPENT
    confirmations = entry.get("confirmations")
    if not isinstance(confirmations, int) or isinstance(confirmations, bool) or confirmations < 0:
        return RewardStatus.UNVERIFIED
    if maturity_depth is None or maturity_depth < 1:
        return RewardStatus.UNVERIFIED
    return RewardStatus.MATURED if confirmations >= maturity_depth else RewardStatus.IMMATURE


def maturity_depth_from_core() -> int:
    """Ghost Core consensus.h/wallet.cpp use COINBASE_MATURITY for coinstake spendability."""
    return COINBASE_MATURITY


def identify_reward(block: dict[str, Any], wallet_entries: list[dict[str, Any]],
                    maturity_depth: int | None) -> RewardMatch | None:
    """Match only a wallet-owned stake entry; never infer ownership from block totals."""
    block_hash = block.get("blockhash") or block.get("hash")
    height = block.get("height")
    txid = block.get("coinstake")
    if not isinstance(block_hash, str) or not isinstance(txid, str):
        return None
    candidates = [entry for entry in wallet_entries
                  if isinstance(entry, dict)
                  and entry.get("txid") == txid
                  and entry.get("blockhash") == block_hash
                  and entry.get("category") in {"stake", "orphaned_stake"}]
    if len(candidates) != 1:
        return None
    entry = candidates[0]
    vout = entry.get("vout")
    amount = _atomic(entry.get("reward", entry.get("amount")))
    if not isinstance(vout, int) or isinstance(vout, bool) or amount is None:
        return None
    reward_fields = (block.get("stakereward"), block.get("blockreward"),
                     block.get("treasuryreward"), block.get("gvrreward"))
    completeness = (DataCompleteness.COMPLETE
                    if all(_atomic(value) is not None for value in reward_fields)
                    else DataCompleteness.PARTIAL)
    return RewardMatch(block_hash, height if isinstance(height, int) else None, txid, vout,
                       amount, _status(entry, maturity_depth), True, "listtransactions", completeness)


def _track_reward_in_transaction(db: IntelligenceDB, block: dict[str, Any],
                                 wallet_entries: list[dict[str, Any]], wallet_name: str,
                                 maturity_depth: int | None) -> RewardStatus:
    match = identify_reward(block, wallet_entries, maturity_depth)
    if match is None:
        return RewardStatus.UNVERIFIED
    has_v2_data = "reward_inputs" in block and "reward_outputs" in block
    attribution = attribute_reward(block.get("reward_inputs"), block.get("reward_outputs")) if has_v2_data else None
    wallet_amount = attribution.wallet_reward_atomic if attribution else match.wallet_reward_atomic
    status = match.status if attribution is None or attribution.completeness is DataCompleteness.COMPLETE else RewardStatus.UNVERIFIED
    completeness = attribution.completeness if attribution else match.completeness
    now = utc_now()
    event_key = f"main:{match.block_hash}:{match.txid}:{match.vout}:{wallet_name}"
    db.connection.execute(
        """INSERT OR IGNORE INTO staking_events
            (event_key,network,event_type,block_hash,height,txid,wallet_name,status,detected_at,metadata_json)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (event_key, "main", "staking_reward", match.block_hash, match.block_height, match.txid,
        wallet_name, status.value, now, '{"owner_verified":true}'),
    )
    event = db.connection.execute("SELECT id,status FROM staking_events WHERE event_key=?", (event_key,)).fetchone()
    if event is None:
        raise RuntimeError("reward event was not persisted")
    old_status = event["status"]
    db.connection.execute(
            """INSERT INTO staking_rewards
            (event_id,network,block_hash,coinstake_txid,wallet_name,vout,wallet_reward_atomic,
             stake_reward_atomic,block_reward_atomic,treasury_reward_atomic,gvr_reward_atomic,
             maturity_height,matured_at,spent_status,status,data_completeness,source_rpc,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(event_id) DO UPDATE SET status=excluded.status,
             wallet_reward_atomic=excluded.wallet_reward_atomic,
             data_completeness=excluded.data_completeness,updated_at=excluded.updated_at""",
        (event["id"], "main", match.block_hash, match.txid, wallet_name, match.vout,
         wallet_amount, _atomic(block.get("stakereward")), _atomic(block.get("blockreward")),
         _atomic(block.get("treasuryreward")), _atomic(block.get("gvrreward")),
         match.block_height + maturity_depth if match.block_height is not None and maturity_depth else None,
         now if status == RewardStatus.MATURED else None, "UNKNOWN", status.value,
         completeness.value, "getblockreward+listtransactions+attribution", now, now),
    )
    reward_row = db.connection.execute("SELECT id FROM staking_rewards WHERE event_id=?", (event["id"],)).fetchone()
    if reward_row is None:
        raise RuntimeError("reward record was not persisted")
    reward_id = reward_row["id"]
    if attribution is not None:
        for item in block.get("reward_inputs") or []:
            if not isinstance(item, dict):
                continue
            db.connection.execute(
                "INSERT OR REPLACE INTO reward_inputs(reward_id,prev_txid,prev_vout,value_atomic,ownership_status,source_rpc,completeness) VALUES(?,?,?,?,?,?,?)",
                (reward_id, item.get("prev_txid", "unknown"), item.get("prev_vout", -1),
                 _atomic(item.get("value_atomic", item.get("value"))),
                 "CONFIRMED" if item.get("owner_verified") is True else "UNKNOWN",
                 item.get("source_rpc", "gettransaction"), attribution.completeness.value),
            )
        for item in block.get("reward_outputs") or []:
            if not isinstance(item, dict):
                continue
            db.connection.execute(
                "INSERT OR REPLACE INTO reward_outputs(reward_id,vout,value_atomic,output_class,ownership_status,source_rpc,completeness) VALUES(?,?,?,?,?,?,?)",
                (reward_id, item.get("vout", -1), _atomic(item.get("value_atomic", item.get("value"))),
                 item.get("output_class", "unknown"),
                 "CONFIRMED" if item.get("owner_verified") is True else "UNKNOWN",
                 item.get("source_rpc", "wallet-rpc"), attribution.completeness.value),
            )
        db.connection.execute(
            "INSERT OR IGNORE INTO reward_evidence(reward_id,evidence_type,source_rpc,source_reference,verified,created_at) VALUES(?,?,?,?,?,?)",
            (reward_id, "wallet_ownership", "wallet-rpc", match.txid, int(attribution.ownership_verified), now),
        )
    if old_status != status.value:
        db.connection.execute(
                "INSERT INTO reward_status_history(event_id,old_status,new_status,changed_at,reason) VALUES(?,?,?,?,?)",
            (event["id"], old_status, status.value, now, "reconciliation"),
        )
    db.connection.execute("UPDATE staking_events SET status=? WHERE id=?", (status.value, event["id"]))
    return status


def track_reward(db: IntelligenceDB, block: dict[str, Any], wallet_entries: list[dict[str, Any]],
                 wallet_name: str = "ghostmain", maturity_depth: int | None = None) -> RewardStatus:
    db.connection.execute("BEGIN IMMEDIATE")
    try:
        result = _track_reward_in_transaction(db, block, wallet_entries, wallet_name, maturity_depth)
        db.connection.commit()
        return result
    except Exception:
        db.connection.rollback()
        raise


def reconcile_wallet(db: IntelligenceDB, wallet_entries: list[dict[str, Any]], balances: dict[str, Any] | None) -> str | None:
    if not isinstance(balances, dict):
        return "RECONCILIATION_WARNING: wallet balances unavailable"
    known = {entry.get("txid") for entry in wallet_entries if isinstance(entry, dict)}
    missing = db.connection.execute("SELECT coinstake_txid FROM staking_rewards WHERE spent_status='UNKNOWN'").fetchall()
    if any(row[0] not in known for row in missing):
        return "RECONCILIATION_WARNING: reward history and wallet history differ"
    return None


def refresh_reward_lifecycle(db: IntelligenceDB, current_height: int,
                            maturity_depth: int = COINBASE_MATURITY) -> int:
    """Advance only IMMATURE rewards; orphaned and unverified records never mature."""
    if isinstance(current_height, bool) or not isinstance(current_height, int) or current_height < 0:
        return 0
    if isinstance(maturity_depth, bool) or not isinstance(maturity_depth, int) or maturity_depth < 1:
        return 0
    now = utc_now()
    rows = db.connection.execute(
        "SELECT id,event_id,status,maturity_height FROM staking_rewards WHERE status='IMMATURE'"
    ).fetchall()
    changed = 0
    db.connection.execute("BEGIN IMMEDIATE")
    try:
        for row in rows:
            target = row["maturity_height"]
            if not isinstance(target, int) or current_height < target:
                continue
            db.connection.execute(
                "INSERT INTO reward_status_history(event_id,old_status,new_status,changed_at,reason) VALUES(?,?,?,?,?)",
                (row["event_id"], "IMMATURE", "MATURED", now, "chain tip maturity"),
            )
            db.connection.execute(
                "UPDATE staking_rewards SET status='MATURED',matured_at=?,updated_at=? WHERE id=?",
                (now, now, row["id"]),
            )
            db.connection.execute("UPDATE staking_events SET status='MATURED' WHERE id=?", (row["event_id"],))
            changed += 1
        db.connection.commit()
    except Exception:
        db.connection.rollback()
        raise
    return changed


def financial_summary(db: IntelligenceDB, wallet_name: str = "ghostmain") -> dict[str, int]:
    """Aggregate only wallet rewards with verified lifecycle status."""
    rows = db.connection.execute(
        "SELECT status,data_completeness,wallet_reward_atomic FROM staking_rewards WHERE wallet_name=?", (wallet_name,)
    ).fetchall()
    summary = {"confirmed": 0, "pending": 0, "orphaned": 0, "spent": 0, "unverified": 0}
    for row in rows:
        amount = row["wallet_reward_atomic"]
        if not isinstance(amount, int) or amount < 0:
            continue
        status = row["status"]
        complete = row["data_completeness"] == DataCompleteness.COMPLETE.value
        if status == "MATURED" and complete and amount > 0:
            summary["confirmed"] += amount
        elif status == "IMMATURE":
            summary["pending"] += amount
        elif status == "ORPHANED":
            summary["orphaned"] += amount
        elif status == "SPENT":
            summary["spent"] += amount
        else:
            summary["unverified"] += amount
    return summary
