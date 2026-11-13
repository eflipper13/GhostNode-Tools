# G5.8 Historical Reward Engine

## Pipeline

The block planner performs read-only RPC first. For a plan containing PoS
blocks it loads bounded wallet history once, then builds a temporary
`TXID -> blockhash` index. A wallet entry is indexed only when it contains a
valid TXID, blockhash, and non-negative block height, and
`getblockhash(height)` independently returns the same blockhash.

The index is discarded after the plan. Conflicting locations are discarded;
the engine never chooses a branch heuristically. This prevents a stale wallet
entry from authorizing historical lookup after a reorganization.

## Prevout evidence

`PrevoutResolver` uses the following order:

1. `gettxout(txid, vout)` for a currently unspent output;
2. `getrawtransaction(txid, 1, blockhash)` only with a verified blockhash;
3. `UNKNOWN` when no independent historical location is available.

It validates TXID, VOUT, returned TXID, blockhash, output existence, and value.
It does not infer a value from the current coinstake or from output ordering.

## Completeness and accounting

Missing prevouts, incomplete wallet history, failed RPC, unknown ownership, or
ambiguous output classes remain `UNKNOWN`/`PARTIAL`. They cannot produce a
confirmed wallet income. Principal return and wallet reward remain separate;
treasury and GVR values are not assigned to the wallet without evidence.

## Reorganizations and limits

The history index is plan-scoped and is rebuilt after a chain-state change.
Reorganization handling remains in the existing block planner and writer
transaction. A bounded `listtransactions` history can end in `LIMIT_REACHED`;
that state is not treated as complete evidence.

The method is practical when `chain_blocks` or wallet history supplies a
verified height, but it cannot recover transactions whose block location is
not known and cannot prove completeness beyond the wallet-history limit.

## Tests

Run the offline suite with:

```bash
.venv/bin/pytest -q
.venv/bin/python -m compileall -q ghostnode tests
git diff --check
```

Tests cover current UTXOs, spent historical outputs, invalid responses,
verified blockhash indexing, conflicts, caching, incomplete history, and
conservative attribution.
