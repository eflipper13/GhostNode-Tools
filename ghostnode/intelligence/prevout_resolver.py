"""Conservative, offline-testable historical prevout resolution.

This module deliberately does not modify the collector, database schema, or RPC
allowlist.  The caller supplies a read-only RPC callable with the project's
``rpc(method, args) -> (value, error)`` contract and an optional, already
verified TXID-to-blockhash index.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Sequence


class PrevoutStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"


@dataclass(frozen=True)
class PrevoutResult:
    status: PrevoutStatus
    txid: str
    vout: int
    value: int | float | None = None
    blockhash: str | None = None
    source: str | None = None
    transaction: Mapping[str, Any] | None = None
    reason: str | None = None


RpcCall = Callable[[str, list[Any]], tuple[Any, str | None]]
_TXID = re.compile(r"^[0-9a-fA-F]{64}$")
_BLOCKHASH = _TXID


def _valid_value(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value >= 0 and (not isinstance(value, float) or math.isfinite(value))


def _blockhash_from_context(context: Mapping[str, Any] | None, txid: str) -> str | None:
    if not context:
        return None
    value = context.get(txid)
    if isinstance(value, str) and _BLOCKHASH.fullmatch(value):
        return value
    return None


class PrevoutResolver:
    """Resolve one or more prevouts without guessing historical data."""

    def __init__(self, rpc: RpcCall):
        self._rpc = rpc

    def resolve(self, prev_txid: str, prev_vout: int,
                block_context: Mapping[str, Any] | None = None) -> PrevoutResult:
        if not isinstance(prev_txid, str) or not _TXID.fullmatch(prev_txid):
            return PrevoutResult(PrevoutStatus.INVALID, str(prev_txid), prev_vout,
                                 reason="invalid transaction id")
        if isinstance(prev_vout, bool) or not isinstance(prev_vout, int) or prev_vout < 0:
            return PrevoutResult(PrevoutStatus.INVALID, prev_txid, prev_vout,
                                 reason="invalid vout")

        # First source: an unspent output may be resolved without txindex.
        utxo, error = self._rpc("gettxout", [prev_txid, prev_vout])
        if error is None and utxo is not None:
            return self._from_utxo(utxo, prev_txid, prev_vout)

        # Second/third sources require an independently verified blockhash.
        blockhash = _blockhash_from_context(block_context, prev_txid)
        if blockhash is None:
            return PrevoutResult(PrevoutStatus.UNKNOWN, prev_txid, prev_vout,
                                 reason="no verified historical blockhash")
        transaction, tx_error = self._rpc("getrawtransaction", [prev_txid, 1, blockhash])
        if tx_error is not None or transaction is None:
            return PrevoutResult(PrevoutStatus.UNKNOWN, prev_txid, prev_vout,
                                 blockhash=blockhash, reason="historical transaction unavailable")
        return self._from_transaction(transaction, prev_txid, prev_vout, blockhash)

    def resolve_many(self, references: Sequence[tuple[str, int]],
                     block_context: Mapping[str, Any] | None = None) -> list[PrevoutResult]:
        seen: set[tuple[str, int]] = set()
        results: list[PrevoutResult] = []
        for txid, vout in references:
            key = (txid, vout)
            if key in seen:
                results.append(PrevoutResult(PrevoutStatus.INVALID, str(txid), vout,
                                             reason="duplicate prevout"))
            else:
                seen.add(key)
                results.append(self.resolve(txid, vout, block_context))
        return results

    @staticmethod
    def _from_utxo(value: Any, txid: str, vout: int) -> PrevoutResult:
        if not isinstance(value, Mapping):
            return PrevoutResult(PrevoutStatus.INVALID, txid, vout,
                                 reason="gettxout returned a non-object")
        amount = value.get("value")
        if not _valid_value(amount):
            return PrevoutResult(PrevoutStatus.INVALID, txid, vout,
                                 reason="invalid UTXO value")
        return PrevoutResult(PrevoutStatus.VERIFIED, txid, vout, amount,
                             source="gettxout", transaction=value)

    @staticmethod
    def _from_transaction(value: Any, txid: str, vout: int,
                          blockhash: str) -> PrevoutResult:
        if not isinstance(value, Mapping):
            return PrevoutResult(PrevoutStatus.INVALID, txid, vout, blockhash=blockhash,
                                 reason="transaction response is not an object")
        if value.get("txid") != txid:
            return PrevoutResult(PrevoutStatus.INVALID, txid, vout, blockhash=blockhash,
                                 reason="transaction id mismatch")
        response_blockhash = value.get("blockhash")
        if response_blockhash is not None and response_blockhash != blockhash:
            return PrevoutResult(PrevoutStatus.INVALID, txid, vout, blockhash=blockhash,
                                 reason="blockhash mismatch")
        outputs = value.get("vout")
        if not isinstance(outputs, list) or vout >= len(outputs):
            return PrevoutResult(PrevoutStatus.INVALID, txid, vout, blockhash=blockhash,
                                 reason="vout is absent")
        output = outputs[vout]
        if not isinstance(output, Mapping) or not _valid_value(output.get("value")):
            return PrevoutResult(PrevoutStatus.INVALID, txid, vout, blockhash=blockhash,
                                 reason="invalid historical output")
        return PrevoutResult(PrevoutStatus.VERIFIED, txid, vout, output["value"],
                             blockhash=blockhash, source="getrawtransaction",
                             transaction=value)


def resolve_prevout(rpc: RpcCall, prev_txid: str, prev_vout: int,
                    block_context: Mapping[str, Any] | None = None) -> PrevoutResult:
    """Functional wrapper for callers that do not need a resolver instance."""
    return PrevoutResolver(rpc).resolve(prev_txid, prev_vout, block_context)
