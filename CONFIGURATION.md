# Configuration

| Variable | Default | Meaning |
|---|---|---|
| `GHOSTNODE_CLI_PATH` | `ghost-cli` | Ghost CLI executable |
| `GHOSTNODE_DATADIR` | `~/.ghost` | Ghost Core data directory |
| `GHOSTNODE_SERVICE` | `ghost.service` | Service name for diagnostics |
| `GHOSTNODE_WALLET` | `ghostmain` | Configured wallet name for read-only diagnostics |
| `GHOSTNODE_WALLET_DIR` | unset | Explicit local wallet directory, if known; never inspected by the tool |
| `GHOSTNODE_INTELLIGENCE_DB` | `data/staking_intelligence.sqlite3` | Intelligence database |

The dashboard accepts only `--host 127.0.0.1`; this is enforced at every CLI
launch path. LAN, public, wildcard, and IPv6 binds are rejected. For remote
access use an SSH tunnel or a separately authenticated proxy. Never put RPC
passwords, cookies, tokens, seeds, or wallet keys in repository files or
command-line arguments.
