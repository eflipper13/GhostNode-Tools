# Security policy

This project is read-only with respect to Ghost Core and wallet operations.
Never run it with wallet credentials in command-line arguments or environment
variables. Keep `.cookie`, `ghost.conf`, wallet files, SQLite databases, WAL/SHM
files, and mainnet reports outside the repository.

The dashboard binds to localhost by default and has no authentication. Treat
network exposure as unsafe unless an operator adds an authenticated,
access-controlled proxy. This document is not a guarantee of security or legal
compliance.
