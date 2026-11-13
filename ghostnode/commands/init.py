from __future__ import annotations

import json

import click

from ghostnode.config import Config
from ghostnode.first_run import first_run_report


@click.command("init")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable first-run JSON.")
@click.option("--cli-path", default=Config.cli_path, show_default=True)
@click.option("--datadir", default=Config.datadir, show_default=True)
@click.option("--wallet", "wallet_name", default=Config.wallet_name, show_default=True)
@click.option("--wallet-dir", default=Config.wallet_dir)
@click.option("--rpc-host", default=Config.rpc_host)
@click.option("--rpc-port", default=Config.rpc_port, type=int)
@click.option("--network", "expected_network", default="main", show_default=True)
def init(as_json: bool, cli_path: str, datadir: str, wallet_name: str,
         wallet_dir: str | None, rpc_host: str | None, rpc_port: int | None,
         expected_network: str) -> None:
    """Run the safe, read-only first-run readiness workflow."""
    payload = first_run_report(
        Config(cli_path=cli_path, datadir=datadir, wallet_name=wallet_name,
               wallet_dir=wallet_dir, rpc_host=rpc_host, rpc_port=rpc_port),
        expected_network=expected_network,
    )
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    click.echo(f"First-run status: {payload['status']}")
    click.echo(f"Operating mode: {payload['mode']}")
    for stage in payload["stages"]:
        click.echo(f"{stage['status']}: {stage['name']} — {stage['message']}")
    click.echo("Next steps:")
    for step in payload["next_steps"]:
        click.echo(f"- {step}")
    if payload["status"] == "FAIL":
        raise click.exceptions.Exit(1)
