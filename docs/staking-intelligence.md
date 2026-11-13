# Staking Intelligence 2.1

The implementation is intentionally separate from the web dashboard. It provides a
SQLite foundation and mockable, read-only collectors; it is not enabled by the
dashboard and is not installed as a service by this change.

## Storage

The default deployment path is `data/staking_intelligence.sqlite3`. SQLite is
configured for WAL mode, a busy timeout, foreign keys, UTC timestamps, and
transactional idempotent writes. Missing RPC fields remain `NULL`.

Amounts must be stored in atomic units when a future reward tracker is added.
Raw RPC responses, credentials, addresses, seeds, and private keys must not be
stored.

## Collector design

- snapshots: every 15 minutes;
- block scan: every 60 seconds;
- the first run records a `BASELINE` at the current tip and does not backfill
  historical blocks; subsequent catch-up starts at `chain_state.last_scanned_height + 1`;
- catch-up is bounded by the caller's batch policy and never advances
  `chain_state` past a block whose reward transaction history could not be read;
- each reward separates lifecycle (`MATURED`, `IMMATURE`, etc.) from economic
  data completeness (`COMPLETE`, `PARTIAL`, `UNKNOWN`); a wallet reward may be
  confirmed while block economics remain partial;
- a writer transaction and process lock must prevent overlapping production runs;
- reorgs are represented by inactive blocks and explicit reorg events, not deletes.

Block and reward writes are committed together when wallet history is available.
If reward history cannot be read, the block is retained as `PENDING` and the
chain cursor is left unchanged for a later retry. Wallet transaction history is
read in bounded pages (20 x 1000 entries maximum per block attempt), with
deduplication. The result is explicitly `COMPLETE`, `RPC_ERROR`, or
`LIMIT_REACHED`; only `COMPLETE` can advance the cursor for a PoS block.
Production `getblockreward` currently requires `txindex`, which is not enabled
on the audited node; block-level reward components therefore remain `NULL` and
the record is `PARTIAL`, rather than being inferred from wallet balances.

The scanner budget is distinct from RPC call count. At a 60-second block scan
interval there are 1,440 cycles/day. A snapshot at 15-minute intervals is 96
cycles/day and, with three RPCs per snapshot, 288 RPC calls/day. Block-cycle
RPC count depends on whether a block is already known: a normal cycle uses
`getblockchaininfo`, `getblockhash`, and `getblock`; a PoS block additionally
uses `getblockreward` and bounded `listtransactions` pages.

## Future service

The local runner is available as `python -m ghostnode collector`. It keeps the
block scanner (60 seconds) and snapshots (15 minutes) on independent monotonic
schedules, with a bounded retry backoff after RPC failures. Both writers use
one shared process lock. `--check` does not open the database and `--once` runs
one current snapshot plus one bounded scanner batch. The runner is not installed,
enabled, or started as a systemd unit by this task. Before deployment, validate
the configured RPC whitelist against the production Ghost Core build and review
the proposed systemd restrictions.
