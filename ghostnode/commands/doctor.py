from __future__ import annotations

import json

import click

from ghostnode.config import Config
from ghostnode.doctor import GhostCoreDoctor, report_dict


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable diagnostic JSON.")
@click.option("--cli-path", default=Config.cli_path, show_default=True, help="Path to ghost-cli.")
@click.option("--datadir", default=Config.datadir, show_default=True, help="Ghost Core data directory.")
@click.option("--rpc-host", default=Config.rpc_host, help="Remote RPC host; no credentials are accepted here.")
@click.option("--rpc-port", default=Config.rpc_port, type=int, help="Remote RPC port.")
@click.option("--network", "expected_network", default="main", show_default=True)
def doctor(as_json: bool, cli_path: str, datadir: str, rpc_host: str | None,
           rpc_port: int | None, expected_network: str) -> None:
    """Run safe, read-only Ghost Core detection and diagnostics."""
    checks = GhostCoreDoctor(Config(cli_path=cli_path, datadir=datadir,
                                    rpc_host=rpc_host, rpc_port=rpc_port),
                             expected_network=expected_network).run()
    payload = report_dict(checks)
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        click.echo(f"Overall status: {payload['status']}")
        for check in checks:
            click.echo(f"{check.status}: {check.name} — {check.message}")
    if payload["status"] == "FAIL":
        raise click.exceptions.Exit(1)
