import click

from ghostnode import __version__
from ghostnode.commands.system import system
from ghostnode.commands.status import status
from ghostnode.commands.network import network
from ghostnode.commands.web import web
from ghostnode.commands.collector import collector


@click.group()
@click.version_option(__version__)
def cli() -> None:
    """Read-only diagnostics for Ghost Core hosts."""


cli.add_command(system)
cli.add_command(status)
cli.add_command(network)
cli.add_command(web)
cli.add_command(collector)
