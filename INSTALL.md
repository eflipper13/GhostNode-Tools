# Installation

This guide describes an isolated Debian 12 installation for GhostNode Tools
v0.3.0. It does not install a systemd unit, modify Ghost Core, unlock a wallet,
or create transactions.

## Requirements

- Debian 12 with Python 3.11 and `python3.11-venv` available;
- a local Ghost Core installation and its read-only `ghost-cli`;
- access to the release archive and its published SHA256 checksum.

## Verify and install

Run these commands as the application user in a new installation directory.
Do not copy a production `.cookie`, `ghost.conf`, wallet file, SQLite database,
or secret into the release tree.

```bash
sha256sum -c GhostNode-Tools-v0.3.0.tar.gz.sha256
mkdir -p "$HOME/ghostnode-tools"
tar -xzf GhostNode-Tools-v0.3.0.tar.gz -C "$HOME/ghostnode-tools" --strip-components=1
cd "$HOME/ghostnode-tools"
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-build-isolation --no-deps -e .
python -m pip check
python -m pytest -q
```

The checksum file must come from the same trusted release channel as the
archive. Do not invent or skip hashes. No command above uses `sudo` or changes
system-wide Python packages.

The stable archive and checksum are local release artifacts. Publication is a
separate owner-approved step. The checksum file is kept beside the archive when running
`sha256sum -c`.

## Local configuration

Copy `.env.example` to a user-owned file outside the repository if desired.
Set `GHOSTNODE_CLI_PATH`, `GHOSTNODE_DATADIR`, and
`GHOSTNODE_INTELLIGENCE_DB` to the local installation paths. Do not put RPC
passwords, cookies, bearer tokens, wallet keys, seeds, or unlock passwords in
the repository, command line, or example file. Ghost Core's local CLI/cookie
authentication is used by the operator's existing installation; this project
does not load or unlock wallets.

## Diagnostics and dashboard

```bash
./bin/ghostnode status --json
./bin/ghostnode doctor --json
./bin/ghostnode wallet status --json
./bin/ghostnode wallet setup --json
./bin/ghostnode init --json
./bin/ghostnode web --host 127.0.0.1 --port 44678
```

The dashboard is read-only and defaults to loopback. To enable the optional
dual-address mode, configure `GHOSTNODE_DASHBOARD_MODE=localhost_lan`, an
assigned private `GHOSTNODE_DASHBOARD_LAN_ADDRESS`, and a restrictive
`GHOSTNODE_DASHBOARD_TOKEN_FILE` in a private environment file. The token file
must already exist; GhostNode Tools never generates or logs a default password.
Wildcard, public, multicast, loopback-as-LAN, and IPv6 addresses are rejected.
Plain HTTP on a LAN does not provide confidentiality. For remote viewing,
localhost mode with an SSH tunnel remains preferred:

```bash
ssh -N -L 44678:127.0.0.1:44678 user@node
```

Inspect `CONFIGURATION.md` and `SECURITY.md` before connecting any live node.
Collector operation is a separate, reviewed step and is not started by this
installation guide.

## Stop and remove

Stop the foreground dashboard with `Ctrl-C`. To remove the application, stop
any process started from this directory and remove only the application
directory after verifying its path. Keep Ghost Core's datadir and any approved
backups separate. Do not delete wallet or production database files as part of
application removal.

## Troubleshooting

- `ghost-cli is unavailable`: set `GHOSTNODE_CLI_PATH` to an executable path.
- RPC errors: verify Ghost Core is already running and that the application
  user can use the existing local CLI/cookie permissions; do not unlock the
  wallet or change RPC configuration for this diagnostic tool.
- SQLite permission errors: use a user-owned data directory with restrictive
  permissions; never loosen permissions on a wallet or Ghost datadir.
- bind error: keep `--host 127.0.0.1` and choose an approved local port.
