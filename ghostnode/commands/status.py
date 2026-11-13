import click

from ghostnode.collectors.rpc import collect_rpc
from ghostnode.collectors.service import collect_service
from ghostnode.config import Config
from ghostnode.models.results import Result, Status
from ghostnode.output.render import render_json, render_text


def _overall(*results: Result) -> Status:
    for status in (Status.ERROR, Status.UNKNOWN, Status.WARN):
        if any(result.status == status for result in results):
            return status
    return Status.OK


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Emit stable JSON output.")
@click.option("--cli-path", default=Config.cli_path, show_default=True, help="Path to ghost-cli.")
@click.option("--datadir", default=Config.datadir, show_default=True, help="Ghost Core data directory.")
@click.option("--service", "service_name", default=Config.service, show_default=True, help="systemd service name.")
def status(as_json: bool, cli_path: str, datadir: str, service_name: str) -> None:
    """Show read-only Ghost Core and service diagnostics."""
    config = Config(cli_path=cli_path, datadir=datadir, service=service_name)
    rpc = collect_rpc(config)
    service = collect_service(config)
    result = Result(_overall(rpc, service), {"rpc": rpc.as_dict(), "service": service.as_dict()})
    if result.status in {Status.ERROR, Status.UNKNOWN}:
        result.message = "One or more diagnostic modules are unavailable"
    click.echo(render_json(result) if as_json else render_text(result))
    if result.status == Status.ERROR:
        raise click.exceptions.Exit(1)
