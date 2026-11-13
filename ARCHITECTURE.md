# Architecture

The CLI invokes read-only host and Ghost diagnostics. The RPC adapter validates
an allowlist, serializes typed arguments, uses bounded subprocess timeouts, and
does not use a shell. Dashboard Intelligence views open SQLite read-only.

The collector separates RPC planning from short SQLite writer transactions.
`InstanceLock` prevents concurrent collector instances and `CollectorLock`
protects writer operations. Reward attribution is conservative: incomplete or
unverified evidence cannot become confirmed income.

Systemd files are templates only and are not installed by this release.
