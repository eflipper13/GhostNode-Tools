# AGENTS.md — GhostNode Tools

## Purpose

GhostNode Tools is an open-source toolkit for monitoring and analyzing Ghost
blockchain nodes, staking activity, and operational health.

This document provides guidance for AI coding assistants and autonomous agents
working with the repository or assisting users with installation and
diagnostics.

Safety, transparency, and reproducibility take priority over automation speed.

These instructions are project guidance, not a security boundary. Agents must
also follow their operating environment's permissions and the user's explicit
authorization.

## 1. Project Principles

- Keep GhostNode Tools focused on monitoring, diagnostics, and read-only
  intelligence.
- Preserve compatibility with supported Ghost Core installations.
- Prefer small, auditable changes over broad refactoring.
- Maintain English-language documentation and user-facing messages.
- Avoid unnecessary dependencies, network requests, and background services.
- Never assume a development environment is safe for production operations.
- Do not silently change configuration, permissions, or system state.
- The current public release line is v0.3.2. Verify source, tag, and package
  metadata independently because the CLI/package version may lag the release
  tag.

## 2. Wallet and Blockchain Safety

GhostNode Tools must never require users to disclose:

- Wallet private keys.
- Recovery seeds or mnemonic phrases.
- Wallet unlock passphrases.
- Wallet backup files.
- Unrestricted RPC credentials in chat messages, logs, or issue reports.

Agents must not:

- Send or transfer cryptocurrency.
- Sign transactions.
- Unlock wallets.
- Export private keys.
- Import or replace wallets.
- Modify staking settings without explicit authorization.
- Delete or overwrite blockchain or wallet data.
- Run wallet-modifying RPC commands.

The application is intended to use a restricted, read-only RPC method allowlist.

**Important:** Application-level RPC restrictions do not necessarily restrict
the permissions granted to Ghost Core RPC credentials. Treat those credentials
as sensitive and potentially privileged.

## 3. RPC and Network Security

- Prefer local Ghost Core RPC connections.
- Never expose Ghost Core RPC directly to the public Internet.
- Never print, commit, or transmit RPC authentication secrets.
- Do not bypass the application's RPC allowlist.
- Do not introduce unrestricted RPC execution interfaces.
- Keep the dashboard bound to `127.0.0.1` by default.
- Optional LAN mode may add exactly one explicitly assigned private IPv4
  address. Wildcard, public, multicast, loopback, link-local, and IPv6
  bindings are not supported.
- Use `token_required` LAN authentication by default. `trusted_lan` is an
  explicit operator choice and does not make read-only data private from other
  reachable LAN clients.
- Never bind the dashboard to `0.0.0.0` or an unrestricted IPv6 interface.
- Prefer SSH tunneling for authorized remote dashboard access.
- Do not add external telemetry or outbound transmission of node data without
  explicit approval and a security review.

Do not treat localhost binding as authentication. Other processes with access
to the local host may still be able to reach the dashboard.

## 4. Repository Architecture

Before modifying code, inspect the current repository structure and relevant
modules.

The project includes:

- Ghost Core RPC collection components.
- Node and staking intelligence processing.
- Local data storage and read-only views.
- Command-line utilities.
- A dashboard that is localhost-only by default, with validated optional
  single-address LAN mode.
- Automated tests and installation documentation.

Agents must verify actual module paths and interfaces from the repository before
making changes.

Do not invent APIs, configuration keys, commands, or database schemas.

## 5. Installation Assistance

When helping users install GhostNode Tools:

1. Verify the operating system and Python version.
2. Follow the repository's current `docs/INSTALLATION.md` and `INSTALL.md`.
3. Use an isolated Python virtual environment.
4. Prefer pinned dependencies and hash verification.
5. Keep application files separate from Ghost Core wallet data.
6. Never ask users to upload wallet files or RPC credentials.
7. Explain security implications before recommending configuration changes.
8. Use localhost-only dashboard access unless an explicitly reviewed,
   authenticated LAN mode is required.
9. Verify installation using documented diagnostics.
10. Explain how to stop or uninstall the application without affecting Ghost
    Core.

The v0.3.2 release documentation targets Debian 12 or supported Ubuntu with
Python 3.11. Agents must not assume that other environments have been tested.

The public v0.3.2 tag may still expose the older `0.3.1` Python package/CLI
version string. Report this metadata limitation instead of silently changing
version claims or release contents.

Do not automatically install packages, change firewall rules, create services,
or modify system configuration without appropriate user authorization.

## 6. Development Workflow

Before making changes:

- Inspect `README.md`, `docs/INSTALLATION.md`, `INSTALL.md`, and relevant source
  files.
- Check the current Git branch and working tree.
- Identify whether the environment contains production services or real wallet
  data.
- Define the smallest reasonable change.
- Preserve unrelated user modifications.

During development:

- Prefer deterministic, testable implementations.
- Keep security-sensitive operations explicit.
- Preserve the existing RPC allowlist.
- Use synthetic data in tests.
- Avoid unnecessary dependencies.
- Do not introduce hidden background activity.
- Never silently modify production configuration.

After making changes:

- Run relevant automated tests.
- Check Python syntax and package integrity.
- Review changes for accidental secrets.
- Verify documentation consistency.
- Report changed files and test results.
- Clearly identify unverified assumptions.

Do not claim tests passed unless they were actually executed.

## 7. Testing Rules

Use isolated test environments wherever possible.

Tests must not:

- Access real wallets.
- Submit blockchain transactions.
- Unlock wallets.
- Change production services.
- Modify production databases.
- Depend on real RPC credentials.
- Expose sensitive information in logs.

Prefer mocked RPC responses, synthetic fixtures, and temporary databases.

Before publishing changes, run the applicable test suite and release validation
checks.

For reward-related changes, include tests for exact atomic values, Ghost PoS
identification, 101-confirmation maturity, idempotency, reorg handling, and
the rule that PARTIAL, UNKNOWN, UNVERIFIED, or ORPHANED data cannot increase
confirmed income.

## 8. Data and Privacy

Node information and staking statistics may reveal operational or financial
details.

Agents must:

- Minimize unnecessary data collection.
- Avoid exposing wallet addresses or transaction identifiers in public logs.
- Sanitize errors before displaying them.
- Avoid uploading local databases to external services.
- Never include real user data in examples or test fixtures without explicit
  authorization.
- Treat diagnostic output as potentially sensitive.

The public donation address in the README is intentionally published. Its
presence does not authorize access to the owner's wallet.

The private Donations observer and dashboard wrapper are deployment-local
extensions. They must remain outside public source exports, release archives,
and pull requests.

## 9. Documentation Standards

All public-facing project materials must use clear English.

This includes:

- README and installation guides.
- Security documentation.
- CLI help and error messages.
- Dashboard labels.
- Release notes.
- Contributor guidance.
- Agent instructions.

Documentation must distinguish between implemented features, experimental
capabilities, and future plans.

Do not present proposed features as available functionality.

Document the distinction between wallet-owned staking rewards and network-wide
block reward components. With `txindex` disabled, unavailable network-wide
components must remain NULL/UNKNOWN rather than being inferred.

## 10. Release and GitHub Operations

Agents must not independently:

- Create public repositories.
- Publish GitHub Releases.
- Push code to remote repositories.
- Force-push branches.
- Rewrite public Git history.
- Publish release assets.
- Change repository visibility.

These actions require explicit authorization from the repository owner.

Before an authorized release, verify:

- Git commit identity.
- Clean working tree.
- Release archive integrity.
- Dependency lockfile.
- Installation instructions.
- Checksums.
- Secret scanning.
- Test results.
- Consistency between published source and release assets.

Never publish private wallet-monitoring functionality or production-specific
files accidentally.

## 11. Production Change Policy

Read-only inspection is preferred.

Agents must obtain explicit authorization before:

- Restarting Ghost Core.
- Changing systemd services.
- Modifying cron jobs.
- Changing firewall rules.
- Altering production configuration.
- Writing to production databases.
- Changing staking settings.
- Installing persistent background services.

Never treat a request for diagnostics as permission to make production changes.

For high-risk or irreversible operations, explain the impact and recovery
procedure before proceeding.

When production changes are explicitly authorized, preserve the current
runtime, private configuration, SQLite database, locks, logs, backups, and
private Donations integration separately from public application source. Back
up affected files and database state before a cutover, verify one collector
instance, and keep a tested rollback path. Documentation-only changes do not
require a service restart.

## 12. Current Operational Boundaries

- The public application is read-only with respect to Ghost Core and wallets;
  it does not create, unlock, encrypt, restore, or transact with wallets.
- Collector writes are limited to the configured local SQLite intelligence
  database and must preserve atomicity, idempotency, and reorg handling.
- Production-only services or wrappers must never be inferred from the public
  checkout; inspect their effective systemd unit and private configuration.

## 13. Agent Communication

Agents should communicate clearly and distinguish:

- Observed facts.
- Test results.
- Assumptions.
- Recommendations.
- Unverified risks.

When an action cannot be completed safely, explain the blocker rather than
bypassing security controls.

When reporting work, include:

- What was inspected.
- What was changed.
- What was tested.
- What remains uncertain.
- Whether production systems were affected.

The preferred behavior is to stop and ask for authorization rather than guess
when wallet security, production integrity, or public publication is at stake.

## 13. Scope of Agent Autonomy

Agents may perform routine repository inspection, documentation review, code
analysis, and isolated testing within their granted permissions.

Agents may propose improvements and prepare changes for review.

Agents must not interpret this document as blanket permission to execute system
modifications, access wallets, or publish code.

The user's explicit instructions and the execution environment's security
restrictions always apply.

---

**GhostNode Tools — Read-only by design. Security-conscious by default.**
