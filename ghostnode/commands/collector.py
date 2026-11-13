from __future__ import annotations

import logging
import os

import click

from ghostnode.config import Config
from ghostnode.intelligence.runner import CollectorRunner, LOG, install_signal_handlers


@click.command()
@click.option("--check", is_flag=True, help="Run RPC preflight only; do not open or write the database.")
@click.option("--once", is_flag=True, help="Run one snapshot and one bounded block-scanner batch.")
@click.option("--db-path", default=lambda: os.environ.get("GHOSTNODE_INTELLIGENCE_DB", "data/staking_intelligence.sqlite3"), show_default=True)
@click.option("--lock-path", default=None)
@click.option("--batch-size", default=100, type=click.IntRange(min=1), show_default=True)
@click.option("--cli-path", default=Config.cli_path, show_default=True)
@click.option("--datadir", default=Config.datadir, show_default=True)
@click.option("--service", "service_name", default=Config.service, show_default=True)
def collector(check: bool, once: bool, db_path: str, lock_path: str | None,
              batch_size: int, cli_path: str, datadir: str, service_name: str) -> None:
    """Run the read-only Staking Intelligence collector."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    runner = CollectorRunner(Config(cli_path=cli_path, datadir=datadir, service=service_name),
                             db_path=db_path, batch_size=batch_size, lock_path=lock_path)
    if check:
        raise click.exceptions.Exit(runner.check())
    install_signal_handlers(runner)
    if once:
        raise click.exceptions.Exit(runner.once())
    runner.run()
