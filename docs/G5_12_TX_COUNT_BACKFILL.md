# G5.12 transaction-count backfill

`chain_blocks.tx_count` is nullable. New blocks use `getblock.nTx`; when that
field is absent, a complete `tx` array is counted. Unknown or incomplete RPC
responses remain `NULL`.

The bounded helper is dry-run by default:

```text
.venv/bin/python scripts/g512_tx_backfill.py --db data/staking_intelligence.sqlite3 --limit 10
```

It reads the database through SQLite read-only mode and performs at most the
requested number of active blocks. `--apply` is an explicit write operation;
use it only after a separate backup and approval. It updates existing rows
with `NULL` `tx_count` only and can be rerun safely.
