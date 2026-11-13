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

GhostNode Tools uses an application-level allowlist of read-only RPC methods.
However, the Ghost Core RPC credentials supplied to the application may have
broader privileges at the node level. Treat those credentials as sensitive.
Never expose Ghost Core RPC to the public Internet, commit credentials to Git,
or share authentication cookies. Never provide wallet seeds, private keys, or
wallet unlock passphrases. Prefer local RPC access and restrictive filesystem
permissions. GhostNode Tools' read-only behavior does not make unrestricted
Ghost Core RPC credentials read-only.
