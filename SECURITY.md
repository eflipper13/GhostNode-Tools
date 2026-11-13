# Security policy

This project is read-only with respect to Ghost Core and wallet operations.
Never run it with wallet credentials in command-line arguments or environment
variables. Keep `.cookie`, `ghost.conf`, wallet files, SQLite databases, WAL/SHM
files, and mainnet reports outside the repository.

The dashboard is enforced to bind only to `127.0.0.1` and has no
authentication. Remote access should use an SSH tunnel; any reverse proxy
must be separately authenticated and access-controlled. Do not replace the
loopback bind with a LAN or public address. This document is not a guarantee
of security or legal compliance.
