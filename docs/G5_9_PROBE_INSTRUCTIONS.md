# G5.9 Mainnet Validation Probe

The probe is read-only. It opens the configured SQLite database with
`mode=ro`, reads at most ten active PoS rows, calls Ghost Core through the
existing `ghost-cli` adapter, and writes only a JSON report. It does not run
the collector and does not insert attribution records.

Run from the repository in the SSH session where local RPC is available:

```bash
cd /path/to/ghostnode-tools
GHOSTNODE_CLI_PATH=/path/to/ghost-cli \
GHOSTNODE_DATADIR=/path/to/ghost-datadir \
.venv/bin/python scripts/g5_9_mainnet_probe.py \
  --db /path/to/test/data/staking_intelligence.sqlite3 \
  --output /tmp/g5_9_mainnet_validation.json
```

The expected report is:

`/tmp/g5_9_mainnet_validation.json`

The script uses a one-second minimum interval between uncached RPC calls,
never issues more than one request at a time, caches identical calls, and
does not retry failures automatically. Values, addresses, scripts, TXIDs and
other private wallet details are not written to the report; output fields are
reported structurally and monetary results remain `null` unless the existing
adapter can prove them.

Inspect the report before any collector integration. A successful process exit
does not imply complete attribution: `UNKNOWN`, `PARTIAL`, RPC errors, chain
mismatches, and incomplete wallet history must remain visible.
