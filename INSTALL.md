# Installation

This is an isolated local installation. It does not install systemd units or
touch an existing Ghost node.

1. Install Python 3.11 and create a virtual environment.
2. Install the verified lock with `python -m pip install --require-hashes -r requirements.lock`.
3. Install the project with `python -m pip install --no-build-isolation --no-deps -e .`.
4. Copy `.env.example` to a user-owned configuration file and review paths.
5. Run the fixture-only tests.
6. Start the dashboard explicitly on localhost.

The collector requires a compatible read-only `ghost-cli`, but must only be
started after a separate operator review, backup, and migration plan.
