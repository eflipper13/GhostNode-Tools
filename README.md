# GhostNode Tools v0.2.0

Licensed under the MIT License. See [LICENSE](LICENSE).

Free, open-source, community-driven read-only CLI utilities and local
staking-intelligence views for Ghost Core. It is intended for Ghost node
operators who want local diagnostics and conservative staking observations.
It is not an official Ghost Core component. It never sends transactions,
unlocks wallets, or changes node configuration.

## Requirements

- Python 3.11+
- a local virtual environment;
- Ghost Core CLI only when using live read-only integration.

No Ghost Core connection is required for M1.

M2 adds read-only Ghost Core and wallet readiness diagnostics. The portable
defaults are `ghost-cli`, `~/.ghost`, and wallet `ghostmain`; they can be
overridden with command options or environment variables.

## Usage

From this directory:

```bash
./bin/ghostnode --help
./bin/ghostnode system
./bin/ghostnode system --json
GHOSTNODE_CLI_PATH=/path/to/ghost-cli GHOSTNODE_DATADIR=/path/to/datadir ./bin/ghostnode status
./bin/ghostnode status --json
./bin/ghostnode doctor --json
./bin/ghostnode wallet status --json
./bin/ghostnode wallet setup --json
./bin/ghostnode init --json
```

Alternatively:

```bash
python3 -m ghostnode system --json
```

The command only reads host metrics. JSON always has a top-level `status` (`OK`,
`WARN`, `ERROR`, or `UNKNOWN`) and `data` object. Errors additionally include
`message`.

## Tests

```bash
python3 -m pytest -q
```

## Local dashboard

Install dependencies in a local virtual environment only:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-build-isolation --no-deps -e .
./bin/ghostnode web --host 127.0.0.1 --port 44678
```

The dashboard is read-only, uses port `44678`, and is strictly localhost-only:
the launcher rejects `0.0.0.0`, LAN addresses, and public addresses. It
exposes `/` and `/api/status`; it has no wallet or command-execution endpoints.

The dashboard groups diagnostics into Blockchain, Network, System, Service,
Wallet, Staking Intelligence and Alerts. Wallet readiness is read-only and is
shown separately from node health; no wallet-management actions are exposed.
It refreshes every 30 seconds
and has a manual refresh control. Wallet and staking collection only uses
read-only RPC calls; it never loads, unlocks or transacts with a wallet.

Wallet setup guidance covers location uncertainty, encryption, passphrase
security, offline backups, and recovery. It never copies or verifies wallet
files and reports `GUIDANCE_AVAILABLE` until the user explicitly acknowledges
the guidance. It never claims `BACKUP_REPORTED_BY_USER` or `BACKUP_VERIFIED`
without an external, explicitly verified process.

The integrated first-run workflow combines these diagnostics without changing
system state:

```bash
./bin/ghostnode init --json
```

It reports `NODE_ONLY`, `LOCAL_WALLET`, or `REMOTE_NODE` and keeps node health
separate from wallet and staking readiness. Remote RPC does not imply that a
local Ghost Core installation is missing.

Each refresh performs a bounded, synchronous read-only snapshot. The dashboard
has no authentication. For remote use, keep the process bound to localhost and
use an SSH tunnel or a separately hardened, authenticated proxy; do not change
the bind address to expose it directly.
There is no persistent cache yet, so avoid opening many dashboard clients at
once on a constrained node.

## Staking Intelligence collector (local/test use)

The runner is available as `python -m ghostnode collector`. It uses one shared
process lock, a 60-second bounded block scan and a 15-minute snapshot schedule.
`--check` performs only the read-only RPC preflight and does not open or create
the SQLite database. `--once` runs one snapshot and one bounded scanner batch.
The runner is not installed or enabled as a systemd service by this change.

Staking Intelligence calculates wallet share and statistical probabilities from
the node's current `expectedtime`. These are estimates, not guarantees or APY.
Historical blocks, rewards and difficulty series are shown as unavailable
because the current read-only RPC set does not expose historical data. No
synthetic history is generated.

## systemd deployment (manual)

The repository includes unit templates only. Review them before installation;
they are not installed or activated by this release.

```bash
sudo install -m 0644 deploy/ghostnode-dashboard@.service /etc/systemd/system/ghostnode-dashboard@.service
sudo systemctl daemon-reload
sudo systemctl enable --now ghostnode-dashboard.service
sudo systemctl status ghostnode-dashboard.service
sudo journalctl -u ghostnode-dashboard.service -f
sudo systemctl restart ghostnode-dashboard.service
sudo systemctl stop ghostnode-dashboard.service
sudo systemctl disable ghostnode-dashboard.service
```

The unit runs as `etcmc`, uses the project `.venv`, and passes the production
`ghost-cli` path through environment configuration. The panel has no login;
keep it on the trusted LAN and do not expose it publicly.

The intelligence collector unit is separate and is not enabled by default. It
requires a separate operator review, backup, and migration plan.

```bash
sudo install -d -m 0750 "$HOME/ghostnode-tools/data"
sudo install -m 0644 deploy/ghostnode-intelligence-collector@.service /etc/systemd/system/ghostnode-intelligence-collector@.service
sudo systemd-analyze verify /etc/systemd/system/ghostnode-intelligence-collector.service
sudo systemctl daemon-reload
sudo systemctl enable --now ghostnode-intelligence-collector.service
```

The collector health API preserves the legacy top-level `status` (`OK` or
`NOT STARTED`) for compatibility. The precise lifecycle state is exposed as
`collector_status`: `NOT_STARTED`, `BASELINE_ESTABLISHED`, `RUNNING`,
`SUCCESS`, `PARTIAL`, or `FAILED`.

### Collector locking contract

`InstanceLock` excludes a second collector instance for the lifetime of the
runner. `CollectorLock` is held only around short SQLite writer operations;
RPC preparation remains outside that writer lock. Independent callers of
`collect_snapshot()` and `scan_catch_up()` acquire the shared instance lock by
default and therefore must not call either function recursively while already
holding that same lock. A caller that already owns the instance lock may use
`scan_catch_up(..., external_lock=True)` and remains responsible for the full
lock lifecycle. The runner uses its own phase-separated methods and does not
invoke these wrappers recursively.

The PoS fixture in `tests/fixtures/ghost_pos_block_1658462_fragment.json` is
an explicitly marked fragment: it contains only the block hash, height,
transaction ID and the supplied `OP_ISCOINSTAKE` script marker. Unknown input,
stake-address and other block fields are intentionally not invented.

## Support the Project

GhostNode Tools is free and open-source software.

If you find it useful and would like to support its development, voluntary
GHOST donations are welcome.

GHOST donation address: GZKRMKqiHp6WsVy9DsNAD9arSSK66Pv5Hv

Donations are entirely optional. All features remain free.
