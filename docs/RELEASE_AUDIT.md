# GhostNode Tools — Open Source Release Candidate v0.1

Status: **READY FOR PUBLICATION**

This directory is an isolated release candidate. The production checkout,
SQLite database, Ghost Core, wallet, RPC service, and systemd services were not
modified or started by the release work.

## Scope

- Source was copied from the working tree with `.git`, virtual environments,
  runtime data, SQLite files, locks, backups, generated mainnet reports, and
  archives excluded.
- Dashboard defaults to `127.0.0.1`.
- Unit files are templates only; they were not installed, reloaded, enabled, or
  started.
- No production RPC, wallet operation, migration, collector, commit, or push
  was performed.

## Validation

- Python compilation: PASS (`python -m compileall -q ghostnode scripts`).
- Shell syntax: PASS (`bash -n scripts/*.sh`).
- Git diff check: PASS in the isolated copy.
- Fresh lock-based environment: PASS (`pip check`, editable install, and full
  pytest: 183 passed).
- `systemd-analyze verify`: PASS on temporary units with the RC path
  substituted; no unit was installed or activated.

## Release review notes

1. A real-chain fixture was replaced with a synthetic PoS fixture preserving
   the parser schema and test properties. No real transaction/address data is
   required by the public RC tests.
2. The official project license is MIT with copyright holder `eflipper13`.
3. A production service installation, RPC, database migration, and publication
   were not performed.

## Verdict

The candidate passed the offline release gate and is ready for manual owner
approval and publication. This report does not authorize or perform GitHub
publication.

The final archive checksum is recorded alongside the archive in its external
`SHA256SUMS` file.
