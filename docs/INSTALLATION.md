# GhostNode Tools Installation

This guide installs GhostNode Tools v0.3.2 in an isolated user-owned
directory on Debian 12 or Ubuntu. The project is a read-only diagnostics and
local staking-intelligence tool; it does not install Ghost Core, create or
unlock wallets, send transactions, or change node configuration.

## Requirements

- Debian 12 or a supported Ubuntu release;
- Python 3.11 and the matching virtual-environment package;
- Git and a working shell;
- Ghost Core installed separately when live RPC diagnostics are required;
- an existing `ghost-cli` executable that can authenticate to the intended
  Ghost Core node using its normal local or remote configuration.

The diagnostics can be imported and exercised without a live Ghost Core node.
Live status, wallet-readiness, staking and collector operations require the
corresponding Ghost Core RPC access.

Install the Debian packages as an administrator, if they are not already
available:

```bash
sudo apt update
sudo apt install -y git python3.11 python3.11-venv
```

On Ubuntu, use the distribution's available Python 3.11 and virtual-
environment package names if they differ.

## Download the v0.3.2 source

The public release is identified by the `v0.3.2` Git tag:

```bash
mkdir -p "$HOME/src"
git clone --branch v0.3.2 --depth 1 \
  https://github.com/eflipper13/GhostNode-Tools.git \
  "$HOME/src/GhostNode-Tools"
cd "$HOME/src/GhostNode-Tools"
```

If a release archive and checksum are supplied through a trusted release
channel, verify them before extraction:

```bash
sha256sum -c GhostNode-Tools-v0.3.2.tar.gz.sha256
mkdir -p "$HOME/src/GhostNode-Tools"
tar -xzf GhostNode-Tools-v0.3.2.tar.gz \
  -C "$HOME/src/GhostNode-Tools" --strip-components=1
cd "$HOME/src/GhostNode-Tools"
```

The v0.3.2 release currently provides the Git tag as the source reference; do
not assume an archive asset exists if it is not listed on the release page.

Do not copy a Ghost Core datadir, wallet files, cookie files, SQLite database,
or private configuration into this source directory.

The public release tag is v0.3.2. The current Python package metadata and CLI
version string may still report 0.3.1; this does not change the tag or source
being installed and is a packaging metadata limitation to be resolved in a
future release.

## Create the isolated environment

Use a virtual environment and the repository's hash-locked dependencies:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-build-isolation --no-deps -e .
python -m pip check
```

The editable install is local; it does not install GhostNode Tools globally.
The lock file is the source of truth for the reproducible dependency set.

## Configure read-only Ghost Core access

GhostNode Tools invokes the configured `ghost-cli`. It does not manage RPC
credentials, cookies, wallets, or Ghost Core configuration.

For a local node, set only the paths that differ from the safe defaults:

```bash
export GHOSTNODE_CLI_PATH="$HOME/ghost-0.23.1.0/ghost-cli"
export GHOSTNODE_DATADIR="$HOME/.ghost"
export GHOSTNODE_WALLET=ghostmain
```

For a remote node, configure endpoint routing without putting passwords or
cookies in the command line:

```bash
export GHOSTNODE_RPC_HOST=node.example
export GHOSTNODE_RPC_PORT=51725
```

Protect the Ghost Core authentication mechanism separately. Do not place
`rpcpassword`, cookies, private keys, seed phrases, wallet passwords, or
bearer tokens in `.env.example`, Git, shell history, or issue reports.

The available configuration names and safe defaults are documented in
[`.env.example`](../.env.example) and [`CONFIGURATION.md`](../CONFIGURATION.md).

## First diagnostics

Run the read-only diagnostics from the project directory:

```bash
./bin/ghostnode --help
./bin/ghostnode status --json
./bin/ghostnode doctor --json
./bin/ghostnode wallet status --json
./bin/ghostnode wallet setup --json
./bin/ghostnode init --json
```

These commands report unavailable services as diagnostics. They do not install
Ghost Core, create/load/unlock/encrypt wallets, create or verify backups, send
transactions, or modify SQLite.

## Start the dashboard locally

The safest default is a foreground, loopback-only dashboard:

```bash
./bin/ghostnode web --host 127.0.0.1 --port 44678
```

Open `http://127.0.0.1:44678` on the node. Stop the foreground process with
`Ctrl-C`. The dashboard is read-only and has no login in localhost-only mode;
do not bind it to a public or wildcard address.

For remote viewing, keep the dashboard on localhost and use an SSH tunnel:

```bash
ssh -N -L 44678:127.0.0.1:44678 user@node
```

Then open `http://127.0.0.1:44678` on the client machine. The optional
dual-address LAN mode requires an explicitly assigned private IPv4 address and
the documented bearer-token configuration. Review [`SECURITY.md`](../SECURITY.md)
and [`docs/V0_3_NETWORK_ACCESS.md`](V0_3_NETWORK_ACCESS.md) before enabling it.

## Start the collector only after review

The collector is separate from the dashboard and writes snapshots and chain
intelligence to the configured SQLite database. It is not started by the
installation steps above.

Run a read-only RPC preflight first:

```bash
./bin/ghostnode collector --check \
  --db-path "$HOME/ghostnode-tools-data/staking_intelligence.sqlite3"
```

For a bounded foreground test, use a test database and explicit review:

```bash
./bin/ghostnode collector --once \
  --db-path "$HOME/ghostnode-tools-data/staking_intelligence.sqlite3"
```

Do not point a test run at a production database. Back up an existing database
and review the lock, ownership, schema and rollback procedure before enabling a
continuous collector.

The repository contains parameterized systemd unit templates. They are examples
only and are not installed or enabled automatically. If systemd operation is
required, review the templates first:

```bash
sudo install -m 0644 deploy/ghostnode-dashboard@.service \
  /etc/systemd/system/ghostnode-dashboard@.service
sudo install -m 0644 deploy/ghostnode-intelligence-collector@.service \
  /etc/systemd/system/ghostnode-intelligence-collector@.service
sudo systemd-analyze verify \
  /etc/systemd/system/ghostnode-dashboard@.service \
  /etc/systemd/system/ghostnode-intelligence-collector@.service
```

The templates use the service-user instance name, for example
`ghostnode-dashboard@etcmc.service`, and expect the application at
`%h/ghostnode-tools`. Configure the private environment file and data path for
the chosen user before enabling a service. Do not copy production units or
credentials into the repository.

## Troubleshooting

### `ghost-cli is unavailable`

Set `GHOSTNODE_CLI_PATH` to the executable path and verify it is executable.
GhostNode Tools does not install Ghost Core for you.

### RPC authentication or connection errors

Verify that Ghost Core is already running and that the selected `ghost-cli`
can use the operator's existing authentication setup. Do not put credentials in
the command line and do not unlock the wallet for diagnostics.

### `wallet status` is unknown

An RPC error is not proof that a wallet is absent. Check the selected wallet
name, node context, and read-only RPC availability. Remote nodes do not imply
that local Ghost Core is missing.

### Dashboard bind or port errors

Keep the primary dashboard on `127.0.0.1` and choose an unused unprivileged
port. In LAN mode, use one explicitly assigned private IPv4 address; wildcard,
public, multicast, loopback-as-LAN and IPv6 addresses are rejected.

### SQLite permission or lock errors

Use a user-owned data directory with restrictive permissions and ensure only one
collector instance is active. Do not delete a lock or database to bypass an
error. Preserve the database and follow the rollback procedure.

## Safe updates

Keep application code, private configuration, SQLite data, logs and backups in
separate locations. For an update:

1. Read the release notes and verify the archive checksum or Git tag.
2. Back up the SQLite database using a consistent SQLite backup procedure.
3. Stop only services belonging to the old application version, if applicable.
4. Install the new release into a new directory; do not overwrite the old
   directory or copy private data into it.
5. Create a fresh virtual environment and install the new lock file.
6. Run `ghostnode doctor --json`, `ghostnode init --json`, and database
   integrity checks against the intended data path.
7. Start the reviewed service or foreground process and verify localhost-only
   access, singleton collector state, logs, API health and rollback readiness.
8. Keep the previous application directory and backup until the update is
   accepted.

Do not run migrations, recovery or production collector changes merely because
the package was downloaded. Review each release's instructions and rollback
plan first.

## Further reading

- [`README.md`](../README.md)
- [`INSTALL.md`](../INSTALL.md)
- [`CONFIGURATION.md`](../CONFIGURATION.md)
- [`SECURITY.md`](../SECURITY.md)
- [`docs/GHOST_CORE_SETUP.md`](GHOST_CORE_SETUP.md)
- [`docs/staking-intelligence.md`](staking-intelligence.md)
