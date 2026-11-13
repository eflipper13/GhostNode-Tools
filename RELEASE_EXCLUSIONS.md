# Release exclusions

The RC was copied without `.git`, virtual environments, SQLite databases,
WAL/SHM files, lock files, backups, generated caches, mainnet JSON reports, or
Ghost Core configuration and wallet files. These exclusions are intentional and
must remain excluded from any public archive.

The real-chain fixture and RPC probe scripts still require a manual privacy
review before publication because they contain public-chain identifiers and
script/address-shaped fields.
