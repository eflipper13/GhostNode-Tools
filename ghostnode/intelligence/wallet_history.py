"""Build a conservative, per-plan wallet transaction location index."""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping

RPC = Callable[[str, list[Any] | None], tuple[Any, str | None]]
_HASH = re.compile(r"^[0-9a-fA-F]{64}$")


def build_verified_history_index(
    entries: list[dict[str, Any]] | None,
    rpc: RPC,
    blockhash_cache: dict[int, str] | None = None,
) -> dict[str, str]:
    """Return TXID -> blockhash only when wallet metadata is independently verified.

    ``listtransactions`` is treated as a hint, never as proof of a block
    location.  A height is required and ``getblockhash(height)`` must agree
    with the reported blockhash. Conflicts are discarded deterministically.
    """
    verified: dict[str, str] = {}
    conflicts: set[str] = set()
    heights = blockhash_cache if blockhash_cache is not None else {}
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        txid = entry.get("txid")
        blockhash = entry.get("blockhash")
        height = entry.get("blockheight", entry.get("height"))
        if not (isinstance(txid, str) and _HASH.fullmatch(txid)
                and isinstance(blockhash, str) and _HASH.fullmatch(blockhash)
                and isinstance(height, int) and not isinstance(height, bool) and height >= 0):
            continue
        if txid in conflicts:
            continue
        if height not in heights:
            candidate, error = rpc("getblockhash", [height])
            if error or not (isinstance(candidate, str) and _HASH.fullmatch(candidate)):
                continue
            heights[height] = candidate
        if heights[height] != blockhash:
            continue
        previous = verified.get(txid)
        if previous is not None and previous != blockhash:
            verified.pop(txid, None)
            conflicts.add(txid)
        elif txid not in conflicts:
            verified[txid] = blockhash
    return verified


def merge_verified_history_indexes(*indexes: Mapping[str, str]) -> dict[str, str]:
    """Merge indexes while dropping TXIDs that resolve to conflicting branches."""
    result: dict[str, str] = {}
    conflicts: set[str] = set()
    for index in indexes:
        for txid, blockhash in index.items():
            if txid in conflicts:
                continue
            old = result.get(txid)
            if old is not None and old != blockhash:
                result.pop(txid, None)
                conflicts.add(txid)
            else:
                result[txid] = blockhash
    return result
