import click

from ghostnode.collectors.system import collect_system
from ghostnode.output.render import render_json, render_text


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Emit stable JSON output.")
def system(as_json: bool) -> None:
    result = collect_system()
    click.echo(render_json(result) if as_json else render_text(result))
    if result.status.value in {"ERROR", "UNKNOWN"}:
        raise click.exceptions.Exit(1)
