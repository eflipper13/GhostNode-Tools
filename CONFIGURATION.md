# Configuration

| Variable | Default | Meaning |
|---|---|---|
| `GHOSTNODE_CLI_PATH` | `ghost-cli` | Ghost CLI executable |
| `GHOSTNODE_DATADIR` | `~/.ghost` | Ghost Core data directory |
| `GHOSTNODE_SERVICE` | `ghost.service` | Service name for diagnostics |
| `GHOSTNODE_INTELLIGENCE_DB` | `data/staking_intelligence.sqlite3` | Intelligence database |

The dashboard host and port are CLI options. The safe default is
`--host 127.0.0.1`. Never put RPC passwords, cookies, tokens, seeds, or wallet
keys in repository files or command-line arguments.
