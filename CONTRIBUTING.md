# Contributing

Use fixture and mock data only. Do not use production RPC, wallet files, or
production SQLite in tests. Add regression tests for RPC parsing, SQLite
transactions, locks, reorgs, and reward accounting.

Before submitting changes, run the smallest relevant tests, then broader checks
when the change warrants them. Typical final checks are:

```bash
python -m pytest -q
python -m compileall -q ghostnode scripts
git diff --check
python scripts/check_tracked_artifacts.py
```

Do not add generated files, databases, mainnet reports, or credentials.

## Repository map

- `ghostnode/cli.py` and `ghostnode/__main__.py`: CLI entry points.
- `ghostnode/commands/`: Click command implementations.
- `ghostnode/collectors/`: host, RPC, service, wallet, staking, and network
  collection.
- `ghostnode/intelligence/`: SQLite storage, locks, runner, reward attribution,
  prevout resolution, wallet history, diagnostics, and dashboard views.
- `ghostnode/models/results.py`, `ghostnode/presentation.py`, and
  `ghostnode/output/`: shared result, presentation, and rendering structures.
- `ghostnode/web.py` and `ghostnode/templates/dashboard.html`: dashboard
  application and template.
- `tests/test_*.py`: offline pytest suite and synthetic fixtures.
- `scripts/`: maintenance and diagnostic utilities.
- `deploy/`: example systemd units, not active services.
- `docs/`: installation, security-adjacent guidance, implementation design,
  and historical decisions.
- `.github/workflows/ci.yml`: CI commands and artifact policy.

## Targeted testing

Start with the test file that exercises the changed subsystem:

| Change area | Representative tests |
|---|---|
| CLI and command dispatch | `tests/test_status.py`, `tests/test_system.py`, `tests/test_doctor.py`, `tests/test_wallet_cli.py` |
| RPC parsing and probes | `tests/test_rpc.py`, `tests/test_rpc_probe.py`, `tests/test_rpc_schema_probe.py` |
| SQLite, locks, runner, and intelligence | `tests/test_intelligence.py`, `tests/test_runner.py`, `tests/test_wallet_history.py` |
| Rewards and prevout evidence | `tests/test_rewards.py`, `tests/test_reward_adapter.py`, `tests/test_prevout_resolver.py` |
| Network and dashboard | `tests/test_network.py`, `tests/test_web.py`, `tests/test_presentation.py` |
| Wallet diagnostics | `tests/test_wallet.py`, `tests/test_wallet_status.py`, `tests/test_wallet_location.py` |
| Installation and release artifacts | `tests/test_ci_artifact_policy.py`, `tests/test_first_run.py` |

Run a focused file with `python -m pytest -q tests/test_<area>.py`. Use the full
suite for broad behavioral changes or before release-level verification.
