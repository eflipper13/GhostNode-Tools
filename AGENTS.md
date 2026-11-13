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
- Keep the dashboard bound to `127.0.0.1`.
- Do not change dashboard binding to `0.0.0.0`, public IP addresses, or
  unrestricted IPv6 interfaces.
- Use SSH tunneling for authorized remote dashboard access.
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
- A localhost-only dashboard.
- Automated tests and installation documentation.

Agents must verify actual module paths and interfaces from the repository before
making changes.

Do not invent APIs, configuration keys, commands, or database schemas.

## 5. Installation Assistance

When helping users install GhostNode Tools:

1. Verify the operating system and Python version.
2. Follow the repository's current `INSTALL.md`.
3. Use an isolated Python virtual environment.
4. Prefer pinned dependencies and hash verification.
5. Keep application files separate from Ghost Core wallet data.
6. Never ask users to upload wallet files or RPC credentials.
7. Explain security implications before recommending configuration changes.
8. Use localhost-only dashboard access.
9. Verify installation using documented diagnostics.
10. Explain how to stop or uninstall the application without affecting Ghost
    Core.

The v0.1.0 release was validated against Debian 12 and Python 3.11. Agents
must not assume that other environments have been tested.

Do not automatically install packages, change firewall rules, create services,
or modify system configuration without appropriate user authorization.

## 6. Development Workflow

Before making changes:

- Inspect `README.md`, `INSTALL.md`, and relevant source files.
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

## 12. Agent Communication

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
