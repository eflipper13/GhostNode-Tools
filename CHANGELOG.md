# Changelog

## 0.2.0rc1

- Read-only Ghost Core detection and RPC/network diagnostics.
- Wallet readiness diagnostics and safe wallet setup, backup, passphrase, and
  recovery guidance.
- Integrated `ghostnode init` first-run workflow for `NODE_ONLY`,
  `LOCAL_WALLET`, and `REMOTE_NODE` modes.
- Local wallet location metadata detection without opening wallet storage.
- Localhost-only dashboard readiness summary and expanded regression coverage.

This release candidate does not install Ghost Core, change wallet state, create
or verify backups, manage services, or expose RPC publicly.

## 0.1.0

- Initial isolated release candidate.
- Localhost-only dashboard default.
- Portable configuration and systemd templates.
- Read-only Intelligence and conservative reward-accounting test suite.
