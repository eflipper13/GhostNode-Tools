from __future__ import annotations

import json

import click

from ghostnode.config import Config
from ghostnode.setup_guidance import setup_report


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable setup guidance JSON.")
@click.option("--cli-path", default=Config.cli_path, show_default=True, help="Path to ghost-cli.")
@click.option("--datadir", default=Config.datadir, show_default=True, help="Ghost Core data directory.")
@click.option("--rpc-host", default=Config.rpc_host, help="Remote RPC host; no credentials are accepted here.")
@click.option("--rpc-port", default=Config.rpc_port, type=int, help="Remote RPC port.")
def setup(as_json: bool, cli_path: str, datadir: str,
          rpc_host: str | None, rpc_port: int | None) -> None:
    """Show dry-run Ghost Core setup guidance without changing system state."""
    payload = setup_report(Config(cli_path=cli_path, datadir=datadir,
                                  rpc_host=rpc_host, rpc_port=rpc_port))
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    click.echo(f"Setup guidance status: {payload['status']}")
    click.echo(f"Platform: {payload['environment']['system']} / {payload['environment']['architecture']}")
    for action in payload["actions"]:
        click.echo(f"- {action}")
    for limitation in payload["limitations"]:
        click.echo(f"Limitation: {limitation}")
