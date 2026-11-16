# Architecture

The CLI invokes read-only host and Ghost diagnostics. The RPC adapter validates
an allowlist, serializes typed arguments, uses bounded subprocess timeouts, and
does not use a shell. Dashboard Intelligence views open SQLite read-only.

The collector separates RPC planning from short SQLite writer transactions.
`InstanceLock` prevents concurrent collector instances and `CollectorLock`
protects writer operations. Reward attribution is conservative: incomplete or
unverified evidence cannot become confirmed income. Ghost-specific PoS
detection, exact atomic-unit accounting, 101-confirmation maturity, idempotent
processing, and reorg handling are covered by the reward pipeline tests.

`getblockreward` is optional enrichment, not a prerequisite for ordinary block
persistence. When network-wide reward components cannot be verified, they stay
`NULL`/`UNKNOWN`; wallet-owned income is not inferred from totals or balances.

Private Donations and other host-specific wrappers are outside this public
architecture and must remain local-only.

Systemd files are templates only and are not installed by this release.
