"""Offline normalization of Ghost Core PoS RPC data.

This module deliberately does not call production RPC by itself.  The caller
supplies an RPC function and the adapter records UNKNOWN/PARTIAL whenever a
wallet or prevout proof is unavailable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Callable

from ghostnode.intelligence.rewards import DataCompleteness, RewardAttribution, attribute_reward
from ghostnode.intelligence.prevout_resolver import PrevoutResolver, PrevoutStatus

RPC = Callable[[str, list[Any] | None], tuple[Any, str | None]]


class EvidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    UNVERIFIED = "UNVERIFIED"


class OwnershipStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    NOT_OWNED = "NOT_OWNED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class NormalizedInput:
    prev_txid: str | None
    prev_vout: int | None
    value_atomic: int | None
    prevout_script: dict[str, Any] | None
    ownership_status: OwnershipStatus
    evidence_source: str | None
    confidence: EvidenceStatus


@dataclass(frozen=True)
class NormalizedOutput:
    vout: int
    value_atomic: int | None
    output_class: str
    script_pub_key: dict[str, Any] | None
    addresses: tuple[str, ...]
    stakeaddresses: tuple[str, ...]
    is_coinstake: bool
    ownership_status: OwnershipStatus
    evidence_source: str | None
    confidence: EvidenceStatus


@dataclass(frozen=True)
class NormalizedRewardTransaction:
    block_hash: str | None
    block_height: int | None
    txid: str | None
    inputs: tuple[NormalizedInput, ...]
    outputs: tuple[NormalizedOutput, ...]
    status: EvidenceStatus
    attribution: RewardAttribution

    def as_v2_fields(self) -> dict[str, Any]:
        return {
            "reward_inputs": [{"prev_txid": item.prev_txid, "prev_vout": item.prev_vout,
                               "value": item.value_atomic / 100_000_000 if item.value_atomic is not None else None,
                               "owner_verified": item.ownership_status is OwnershipStatus.CONFIRMED,
                               "source_rpc": item.evidence_source or "getrawtransaction"}
                              for item in self.inputs],
            "reward_outputs": [{"vout": item.vout,
                                "value": item.value_atomic / 100_000_000 if item.value_atomic is not None else None,
                                "output_class": item.output_class,
                                "owner_verified": item.ownership_status is OwnershipStatus.CONFIRMED,
                                "source_rpc": item.evidence_source or "getblock"}
                               for item in self.outputs],
        }


def _atomic(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        from decimal import Decimal
        return int(Decimal(str(value)) * Decimal(100_000_000))
    except Exception:
        return None


def _addresses(script: dict[str, Any] | None, key: str) -> tuple[str, ...]:
    values = script.get(key) if isinstance(script, dict) else None
    return tuple(value for value in values if isinstance(value, str)) if isinstance(values, list) else ()


def _ownership(rpc: RPC, addresses: tuple[str, ...]) -> tuple[OwnershipStatus, str | None]:
    if not addresses:
        return OwnershipStatus.UNKNOWN, None
    saw_unknown = False
    for address in addresses:
        info, error = rpc("getaddressinfo", [address])
        if error or not isinstance(info, dict):
            saw_unknown = True
            continue
        if info.get("ismine") is True:
            return OwnershipStatus.CONFIRMED, "getaddressinfo.ismine"
        if info.get("ismine") is False:
            continue
        saw_unknown = True
    return (OwnershipStatus.UNKNOWN if saw_unknown else OwnershipStatus.NOT_OWNED), "getaddressinfo"


def _prevout(rpc: RPC, txid: str, vout: int,
             block_context: dict[str, str] | None = None) -> tuple[int | None, dict[str, Any] | None, OwnershipStatus, str | None]:
    try:
        result = PrevoutResolver(rpc).resolve(txid, vout, block_context)
    except AssertionError:
        # Compatibility with legacy offline RPC doubles that predate gettxout.
        # Production callers use the verified block context and never take this
        # path; an actual RPC failure is not converted into a fallback.
        if block_context is not None:
            return None, None, OwnershipStatus.UNKNOWN, None
        transaction, error = rpc("getrawtransaction", [txid, 1])
        if error or not isinstance(transaction, dict) or transaction.get("txid") not in (None, txid):
            return None, None, OwnershipStatus.UNKNOWN, None
        outputs = transaction.get("vout")
        if not isinstance(outputs, list) or not 0 <= vout < len(outputs) or not isinstance(outputs[vout], dict):
            return None, None, OwnershipStatus.UNKNOWN, None
        output = outputs[vout]
        script = output.get("scriptPubKey") if isinstance(output.get("scriptPubKey"), dict) else None
        value = _atomic(output.get("value"))
        ownership, source = _ownership(rpc, _addresses(script, "addresses"))
        return value, script, ownership, source
    if result.status is not PrevoutStatus.VERIFIED or not isinstance(result.transaction, dict):
        return None, None, OwnershipStatus.UNKNOWN, result.source
    if result.source == "gettxout":
        script = result.transaction.get("scriptPubKey")
        script = script if isinstance(script, dict) else None
        ownership, source = _ownership(rpc, _addresses(script, "addresses"))
        return _atomic(result.value), script, ownership, source or result.source
    outputs = result.transaction.get("vout")
    if not isinstance(outputs, list) or not 0 <= vout < len(outputs) or not isinstance(outputs[vout], dict):
        return None, None, OwnershipStatus.UNKNOWN, result.source
    output = outputs[vout]
    script = output.get("scriptPubKey") if isinstance(output.get("scriptPubKey"), dict) else None
    ownership, source = _ownership(rpc, _addresses(script, "addresses"))
    return _atomic(result.value), script, ownership, source or result.source


def normalize_reward_transaction(block: dict[str, Any], rpc: RPC,
                                  block_context: dict[str, str] | None = None) -> NormalizedRewardTransaction:
    """Normalize one verbosity=2 block without inferring ownership or principal."""
    txs = block.get("tx") if isinstance(block, dict) else None
    tx = txs[0] if isinstance(txs, list) and txs and isinstance(txs[0], dict) else None
    if tx is None:
        empty = attribute_reward([], [])
        return NormalizedRewardTransaction(None, None, None, (), (), EvidenceStatus.UNKNOWN, empty)

    normalized_inputs: list[NormalizedInput] = []
    for item in tx.get("vin", []):
        if not isinstance(item, dict) or not isinstance(item.get("txid"), str) or not isinstance(item.get("vout"), int):
            normalized_inputs.append(NormalizedInput(None, None, None, None, OwnershipStatus.UNKNOWN, None, EvidenceStatus.UNKNOWN))
            continue
        value, script, owner, source = _prevout(rpc, item["txid"], item["vout"], block_context)
        normalized_inputs.append(NormalizedInput(item["txid"], item["vout"], value, script, owner, source, EvidenceStatus.VERIFIED if value is not None else EvidenceStatus.UNKNOWN))

    normalized_outputs: list[NormalizedOutput] = []
    for item in tx.get("vout", []):
        if not isinstance(item, dict) or not isinstance(item.get("n"), int):
            continue
        script = item.get("scriptPubKey") if isinstance(item.get("scriptPubKey"), dict) else None
        addresses = _addresses(script, "addresses")
        owner, source = _ownership(rpc, addresses)
        normalized_outputs.append(NormalizedOutput(
            item["n"], _atomic(item.get("value")), item.get("output_class", "unknown"), script, addresses,
            _addresses(script, "stakeaddresses"), "OP_ISCOINSTAKE" in str(script.get("asm", "")) if script else False,
            owner, source, EvidenceStatus.VERIFIED if owner is OwnershipStatus.CONFIRMED else EvidenceStatus.UNKNOWN,
        ))

    complete_inputs = bool(normalized_inputs) and all(item.value_atomic is not None for item in normalized_inputs)
    # attribute_reward() accepts coin-denominated values; the normalized model
    # remains atomic. Convert only at this boundary to avoid double scaling.
    v2_inputs = [{"prev_txid": item.prev_txid, "prev_vout": item.prev_vout,
                  "value": item.value_atomic / 100_000_000 if item.value_atomic is not None else None}
                 for item in normalized_inputs]
    v2_outputs = [{"vout": item.vout,
                   "value": item.value_atomic / 100_000_000 if item.value_atomic is not None else None,
                   "output_class": item.output_class,
                   "owner_verified": item.ownership_status is OwnershipStatus.CONFIRMED} for item in normalized_outputs]
    allowed = {"principal", "wallet_reward", "unknown"}
    invalid_class = any(item.output_class not in allowed for item in normalized_outputs)
    ambiguous_class = any(item.ownership_status is OwnershipStatus.CONFIRMED and item.output_class == "unknown"
                          for item in normalized_outputs)
    attribution = attribute_reward(v2_inputs, v2_outputs)
    if invalid_class or ambiguous_class:
        attribution = RewardAttribution(
            attribution.input_value_atomic, None, None, None,
            DataCompleteness.PARTIAL, False,
        )
    status = EvidenceStatus.VERIFIED if complete_inputs and attribution.completeness is DataCompleteness.COMPLETE else EvidenceStatus.PARTIAL if normalized_inputs or normalized_outputs else EvidenceStatus.UNKNOWN
    return NormalizedRewardTransaction(block.get("hash"), block.get("height"), tx.get("txid"), tuple(normalized_inputs), tuple(normalized_outputs), status, attribution)
