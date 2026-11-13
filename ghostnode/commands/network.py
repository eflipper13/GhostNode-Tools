import click

from ghostnode.collectors.network import collect_network
from ghostnode.config import Config
from ghostnode.models.results import Status
from ghostnode.output.render import render_json, render_text


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Emit stable JSON output.")
@click.option("--cli-path", default=Config.cli_path, show_default=True, help="Path to ghost-cli.")
@click.option("--datadir", default=Config.datadir, show_default=True, help="Ghost Core data directory.")
def network(as_json: bool, cli_path: str, datadir: str) -> None:
    """Show read-only Ghost Core network diagnostics."""
    result = collect_network(Config(cli_path=cli_path, datadir=datadir))
    click.echo(render_json(result) if as_json else render_text(result))
    if result.status == Status.ERROR:
        raise click.exceptions.Exit(1)
