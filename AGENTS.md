# AGENTS.md - GhostNode Tools

## Scope

GhostNode Tools is a read-only monitoring and staking-intelligence toolkit.
Keep changes small, auditable, reproducible, and in English. The repository is
the public source of truth; private deployments and data stay outside it.

Before work, inspect `git status`, the relevant source and test files, and the
authoritative document linked below. Preserve unrelated worktree changes.

## Safety boundaries

- Never disclose or commit wallet private keys, seeds, unlock passphrases,
  wallet backups, RPC passwords, Ghost Core cookies, bearer tokens, or private
  environment files.
- Never send or sign transactions, unlock wallets, export or import keys,
  change staking settings, modify wallet data, or bypass the read-only RPC
  allowlist.
- Treat application-level RPC restrictions as distinct from the privileges of
  supplied Ghost Core credentials. Prefer local RPC access.
- Keep the dashboard at `127.0.0.1` unless an explicitly reviewed private LAN
  address and `token_required` configuration are involved. Never introduce
  wildcard, public, multicast, loopback-as-LAN, or IPv6 bindings.
- Do not change production services, firewall rules, cron jobs, production
  SQLite databases, Ghost Core configuration, systemd units, or staking state
  unless the user has explicitly authorized that operation.
- Do not silently change permissions or system state. Never publish releases,
  tags, repositories, or credentials.
- Keep private Donations observers, dashboard wrappers, production units,
  logs, backups, wallet data, and monitoring extensions outside public source,
  archives, pull requests, and commits.

## Repository navigation

Read `CONTRIBUTING.md` first for the compact module map and targeted test
workflow.

- CLI and command entry points: `ghostnode/cli.py`, `ghostnode/__main__.py`,
  and `ghostnode/commands/`.
- RPC, host, and network collection: `ghostnode/collectors/rpc.py`,
  `ghostnode/collectors/network.py`, `ghostnode/host.py`, and
  `ghostnode/network.py`.
- Staking, SQLite, rewards, locks, and views:
  `ghostnode/intelligence/`.
- Dashboard: `ghostnode/web.py` and `ghostnode/templates/dashboard.html`.
- Tests: `tests/test_*.py`.
- Deployment examples: `deploy/`.
- CI: `.github/workflows/ci.yml`.

Use exact symbol or filename searches before broad searches. Read task-specific
files rather than whole directories or complete history. Avoid generated data,
complete logs, and unrelated source.

## Authoritative documentation

- Overview and command examples: `README.md`
- Development, navigation, and test targeting: `CONTRIBUTING.md`
- Installation: `INSTALL.md` and `docs/INSTALLATION.md`
- Runtime settings: `CONFIGURATION.md`
- Security: `SECURITY.md`
- Ghost Core setup: `docs/GHOST_CORE_SETUP.md`
- Intelligence design: `docs/staking-intelligence.md`
- Reward engine: `docs/G5_8_HISTORICAL_REWARD_ENGINE.md`
- Release history: `CHANGELOG.md`

Update only the affected source of truth. Use existing documents for detailed
knowledge instead of duplicating it in agent instructions. Preserve historical
documents and distinguish implementation from roadmap or proposal content.

The public `v0.3.2` tag may have Python package metadata or a CLI version
still reporting `0.3.1`, as described in `docs/INSTALLATION.md`. Do not silently
change version numbers or infer that metadata mismatch is a source change.

## Development workflow

- Make the smallest focused change that satisfies the verified requirement.
- Reuse project patterns and preserve unrelated edits.
- Do not modify application source or CI for documentation-only work.
- Use synthetic data and mocks. Never use real wallets, RPC credentials,
  production SQLite, or production services in tests.
- Make security-sensitive behavior explicit and testable.
- For reward changes, cover exact atomic values, Ghost PoS identification,
  101-confirmation maturity, idempotency, reorganization handling, and the rule
  that PARTIAL, UNKNOWN, UNVERIFIED, or ORPHANED evidence cannot increase
  confirmed income.
- Run the smallest relevant tests first, then broader tests when risk requires
  it. Report tests not run and why.

## Git and reporting

Do not commit or push unless explicitly authorized. For authorized commits,
commit only intended files and do not amend or rewrite shared history.

When work is interrupted or handed off, report:

1. Goal.
2. Current branch and commit.
3. Completed and verified work.
4. Changed files.
5. Test results.
6. Remaining work.
7. Unresolved assumptions.
8. Production impact.

Do not create permanent handoff files for routine completed work.

## Autonomy

Routine repository inspection, documentation review, and isolated testing are
allowed. Stop and explain the blocker instead of guessing when wallet security,
production integrity, public publication, or an authorization boundary is
uncertain.
