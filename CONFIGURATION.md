# Configuration

| Variable | Default | Meaning |
|---|---|---|
| `GHOSTNODE_CLI_PATH` | `ghost-cli` | Ghost CLI executable |
| `GHOSTNODE_DATADIR` | `~/.ghost` | Ghost Core data directory |
| `GHOSTNODE_SERVICE` | `ghost.service` | Service name for diagnostics |
| `GHOSTNODE_WALLET` | `ghostmain` | Configured wallet name for read-only diagnostics |
| `GHOSTNODE_WALLET_DIR` | unset | Explicit local wallet directory, if known; never inspected by the tool |
| `GHOSTNODE_INTELLIGENCE_DB` | `data/staking_intelligence.sqlite3` | Intelligence database |
| `GHOSTNODE_DASHBOARD_MODE` | `localhost` | `localhost` or `localhost_lan` |
| `GHOSTNODE_DASHBOARD_LAN_ADDRESS` | unset | One assigned private LAN IPv4 address; never a wildcard |
| `GHOSTNODE_DASHBOARD_PORT` | `44678` | Unprivileged dashboard TCP port |
| `GHOSTNODE_DASHBOARD_TOKEN_FILE` | unset | Private file containing the LAN bearer token |
| `GHOSTNODE_NETWORK_CONFIG` | `~/.config/ghostnode-tools/network.json` | Private atomically written non-secret settings |

The dashboard always includes `127.0.0.1`. In `localhost_lan` mode it adds
exactly the configured assigned private LAN IPv4 address. LAN mode requires a
bearer token from a private file; there is no default password. Wildcard,
multicast, public, loopback-as-LAN, and IPv6 binds are rejected. Network settings
are validated before listeners start and web proposals never apply changes.
Never put RPC passwords, cookies, bearer tokens, seeds, or wallet keys in
repository files or command-line arguments.
