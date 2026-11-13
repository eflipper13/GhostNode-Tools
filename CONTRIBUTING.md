# Contributing

Use fixture and mock data only. Do not use production RPC, wallet files, or
production SQLite in tests. Add regression tests for RPC parsing, SQLite
transactions, locks, reorgs, and reward accounting.

Before submitting changes, run pytest, compileall, and `git diff --check`.
Do not add generated files, databases, mainnet reports, or credentials.
