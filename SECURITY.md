# Security policy

This project is read-only with respect to Ghost Core and wallet operations.
Never run it with wallet credentials in command-line arguments or environment
variables. Keep `.cookie`, `ghost.conf`, wallet files, SQLite databases, WAL/SHM
files, and mainnet reports outside the repository.

The dashboard defaults to `127.0.0.1` and localhost mode has no authentication
because it is loopback-only. Optional LAN mode binds exactly one assigned
private IPv4 address. New LAN configurations use `token_required`, which
requires a bearer token from a private file for every request. An operator may
explicitly select `trusted_lan` for unauthenticated read-only access, but
administrative endpoints remain token-protected. It rejects wildcard,
multicast, public, loopback-as-LAN, and IPv6 addresses. There is no default
password. Plain HTTP on a LAN does not provide
confidentiality; use an appropriately secured HTTPS layer or SSH tunnel when
needed. This document is not a guarantee of security or legal compliance.

The dashboard only displays network settings and accepts validated proposals;
it cannot write systemd units or apply listener changes. Applying a change is
an explicit operator action with a restart and rollback review.

GhostNode Tools uses an application-level allowlist of read-only RPC methods.
However, the Ghost Core RPC credentials supplied to the application may have
broader privileges at the node level. Treat those credentials as sensitive.
Never expose Ghost Core RPC to the public Internet, commit credentials to Git,
or share authentication cookies. Never provide wallet seeds, private keys, or
wallet unlock passphrases. Prefer local RPC access and restrictive filesystem
permissions. GhostNode Tools' read-only behavior does not make unrestricted
Ghost Core RPC credentials read-only.

`ghostnode wallet status` and `ghostnode wallet setup` may display a local
wallet path only when filesystem metadata identifies a supported location.
Treat that output as local operator information. Remote RPC paths, ambiguous
layouts, and unsupported wallet formats remain `WALLET_PATH_UNKNOWN`; the
first-run report redacts local paths. The tool never opens wallet databases.
