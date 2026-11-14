# Changelog

## 0.3.0

- Version-neutral README with a latest-release link.
- Validated dashboard network modes: localhost-only by default, or localhost
  plus one explicitly assigned private LAN IPv4 address.
- Bearer-token authentication for LAN listeners with no default password.
- Read-only network settings display and validated, non-applying change proposals.
- Atomic private network configuration persistence and port-conflict checks.
- First-run network review options with explicit confirmation before persistence.

LAN mode uses plain HTTP unless deployed behind an independently secured HTTPS
layer; GhostNode Tools does not claim confidentiality for plain LAN traffic.

## 0.2.0

- Read-only Ghost Core detection and RPC/network diagnostics.
- Wallet readiness diagnostics and safe wallet setup, backup, passphrase, and
  recovery guidance.
- Integrated `ghostnode init` first-run workflow for `NODE_ONLY`,
  `LOCAL_WALLET`, and `REMOTE_NODE` modes.
- Local wallet location metadata detection without opening wallet storage.
- Localhost-only dashboard readiness summary and expanded regression coverage.

This release does not install Ghost Core, change wallet state, create or
verify backups, manage services, or expose RPC publicly. Ghost Core
  installation, wallet creation, backup, and recovery are guidance-only. The
  first-run workflow is read-only.

## 0.1.0

- Initial isolated release.
- Localhost-only dashboard default.
- Portable configuration and systemd templates.
- Read-only Intelligence and conservative reward-accounting test suite.
