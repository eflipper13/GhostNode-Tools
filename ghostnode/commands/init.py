from __future__ import annotations

import json

import click

from ghostnode.config import Config
from ghostnode.first_run import first_run_report
from ghostnode.network import (NetworkSettings, save_network_settings,
                               validate_network_settings)


@click.command("init")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable first-run JSON.")
@click.option("--cli-path", default=Config.cli_path, show_default=True)
@click.option("--datadir", default=Config.datadir, show_default=True)
@click.option("--wallet", "wallet_name", default=Config.wallet_name, show_default=True)
@click.option("--wallet-dir", default=Config.wallet_dir)
@click.option("--rpc-host", default=Config.rpc_host)
@click.option("--rpc-port", default=Config.rpc_port, type=int)
@click.option("--network", "expected_network", default="main", show_default=True)
@click.option("--network-mode", type=click.Choice(["localhost", "localhost_lan"]), default="localhost",
              show_default=True)
@click.option("--lan-auth-mode", type=click.Choice(["token_required", "trusted_lan"]), default="token_required",
              show_default=True, help="Explicit LAN authentication mode.")
@click.option("--lan-address", default=None, help="Assigned private LAN IPv4 address for localhost_lan mode.")
@click.option("--dashboard-port", default=44678, show_default=True, type=int)
@click.option("--network-config", default=None, help="Private network configuration path.")
@click.option("--apply-network", is_flag=True, help="Persist the reviewed network settings atomically.")
@click.option("--confirm-network", is_flag=True, help="Confirm the explicit network configuration review.")
def init(as_json: bool, cli_path: str, datadir: str, wallet_name: str,
         wallet_dir: str | None, rpc_host: str | None, rpc_port: int | None,
         expected_network: str, network_mode: str, lan_auth_mode: str, lan_address: str | None,
         dashboard_port: int, network_config: str | None,
         apply_network: bool, confirm_network: bool) -> None:
    """Run the safe, read-only first-run readiness workflow."""
    try:
        network = validate_network_settings(NetworkSettings(network_mode, lan_address, dashboard_port, lan_auth_mode))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    network_plan = {**network.as_dict(), "restart_required": True, "applied": False,
                    "security": ("token required for localhost_lan" if network.lan_auth_mode == "token_required"
                                  else "trusted LAN: every reachable client can read the dashboard")}
    if apply_network:
        if not confirm_network:
            raise click.ClickException("--apply-network requires --confirm-network after reviewing the plan")
        try:
            path = save_network_settings(network, network_config)
        except (OSError, ValueError) as exc:
            raise click.ClickException(f"network configuration was not applied: {exc}") from exc
        network_plan.update({"applied": True, "config_path": str(path)})
    payload = first_run_report(
        Config(cli_path=cli_path, datadir=datadir, wallet_name=wallet_name,
               wallet_dir=wallet_dir, rpc_host=rpc_host, rpc_port=rpc_port),
        expected_network=expected_network, network_plan=network_plan,
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
