# GitHub publication preview

Repository owner: `eflipper13`
Repository name: `GhostNode-Tools`

Description: Read-only Ghost Core node monitoring and conservative staking
intelligence tools for Python 3.11.

Topics: `ghost`, `blockchain`, `node-monitoring`, `staking`, `python`,
`open-source`

Visibility: public (planned only; not configured here).

License: MIT

Release assets: `GhostNode-Tools-v0.1.0.tar.gz` and
`GhostNode-Tools-v0.1.0.tar.gz.sha256`

Topics: `ghost`, `ghost-core`, `blockchain`, `node-monitoring`, `staking`,
`python`, `open-source`

## Proposed release

### `v0.1.0 — Initial Public Release`

- Read-only Ghost Core status, network, wallet and staking diagnostics.
- Local dashboard with localhost-safe defaults.
- Fixture- and mock-based staking intelligence tests.
- Conservative reward and reorganization handling with explicit incomplete
  states.
- Portable configuration examples, CI, security guidance and systemd
  templates.

This preview does not create a remote repository, tag, release, or GitHub
connection.

## Release notes

GhostNode Tools v0.1.0 is a read-only local diagnostics and staking-intelligence
release for Ghost Core operators. It includes status, network, wallet and
staking diagnostics, a localhost-only dashboard, conservative lifecycle and
incomplete-data handling, portable configuration examples, and fixture-based
tests.

The release does not send funds, unlock wallets, export keys, expose a public
RPC interface, or include a donation monitor. Historical reward attribution is
conservative and may remain `PARTIAL`, `UNKNOWN`, or unavailable when Ghost
Core data cannot prove ownership or historical inputs. The dashboard has no
authentication; use `127.0.0.1` and an SSH tunnel or a separately hardened
authenticated proxy.

This is not an independent third-party security audit and does not replace
operator review of Ghost Core, wallet permissions, backups, or host security.
