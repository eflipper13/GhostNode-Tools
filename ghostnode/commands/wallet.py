from __future__ import annotations

import json

import click

from ghostnode.config import Config
from ghostnode.setup_guidance import wallet_setup_report
from ghostnode.wallet_status import wallet_status_report


@click.group()
def wallet() -> None:
    """Show safe wallet readiness diagnostics and setup guidance."""


@wallet.command("status")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable wallet status JSON.")
@click.option("--cli-path", default=Config.cli_path, show_default=True)
@click.option("--datadir", default=Config.datadir, show_default=True)
@click.option("--wallet", "wallet_name", default=Config.wallet_name, show_default=True)
@click.option("--wallet-dir", default=Config.wallet_dir)
@click.option("--rpc-host", default=Config.rpc_host)
@click.option("--rpc-port", default=Config.rpc_port, type=int)
def status(as_json: bool, cli_path: str, datadir: str, wallet_name: str,
           wallet_dir: str | None, rpc_host: str | None, rpc_port: int | None) -> None:
    """Check wallet availability without changing wallet state."""
    payload = wallet_status_report(Config(cli_path=cli_path, datadir=datadir,
                                          wallet_name=wallet_name, wallet_dir=wallet_dir,
                                          rpc_host=rpc_host,
                                          rpc_port=rpc_port))
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        click.echo(f"Wallet status: {payload['status']}")
        click.echo(payload["message"])
        for key, value in payload["data"].items():
            click.echo(f"{key}: {value}")
    if payload["status"] == "FAIL":
        raise click.exceptions.Exit(1)


@wallet.command("setup")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable setup guidance JSON.")
@click.option("--cli-path", default=Config.cli_path, show_default=True)
@click.option("--datadir", default=Config.datadir, show_default=True)
@click.option("--wallet", "wallet_name", default=Config.wallet_name, show_default=True)
@click.option("--wallet-dir", default=Config.wallet_dir)
@click.option("--rpc-host", default=Config.rpc_host)
@click.option("--rpc-port", default=Config.rpc_port, type=int)
def setup(as_json: bool, cli_path: str, datadir: str, wallet_name: str,
          wallet_dir: str | None, rpc_host: str | None, rpc_port: int | None) -> None:
    """Explain safe wallet setup choices; never creates or changes a wallet."""
    payload = wallet_setup_report(Config(cli_path=cli_path, datadir=datadir,
                                         wallet_name=wallet_name, wallet_dir=wallet_dir,
                                         rpc_host=rpc_host, rpc_port=rpc_port))
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    click.echo(f"Wallet setup guidance status: {payload['status']}")
    location = payload["wallet_location"]
    click.echo(f"Wallet location: {location['status']}")
    if location.get("path"):
        click.echo(f"Local metadata path: {location['path']}")
    click.echo(location["message"])
    for option in payload["options"]:
        click.echo(f"{option['name']}: {option['guidance']}")
    for item in payload["security"]:
        click.echo(f"Security: {item}")
    for item in payload["backup"]["guidance"]:
        click.echo(f"Backup: {item}")
