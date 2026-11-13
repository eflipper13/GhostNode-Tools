# G5.9-D/E Wallet-Specific Staking Discovery

Run only from an SSH session where the local Ghost RPC is available:

```bash
clear
cd /path/to/ghostnode-tools
GHOSTNODE_CLI_PATH=/path/to/ghost-cli \
GHOSTNODE_DATADIR=/path/to/ghost-datadir \
.venv/bin/python scripts/g5_9_d_wallet_audit.py \
  --output /tmp/g5_9_wallet_discovery.json
```

The probe is read-only, rate-limited, and does not run the collector or write
SQLite. It reports transaction categories, a sanitized UTXO summary, and
sanitized `gettransaction` response shapes for up to four `receive` entries.
It does not output addresses, TXIDs, scripts, amounts, or wallet secrets.

`UNKNOWN`, `PARTIAL`, `LIMIT_REACHED`, RPC errors, and missing ownership proof
remain explicit. A successful process exit does not prove that a wallet
staking event was found.
