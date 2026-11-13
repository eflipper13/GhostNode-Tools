import click

from ghostnode.config import Config
from ghostnode.host import detect_lan_host  # retained for API/test compatibility; explicit host is used


def validate_dashboard_host(host: str) -> str:
    """Allow only the loopback IPv4 bind in the public v0.1 dashboard."""
    if host != "127.0.0.1":
        raise click.ClickException(
            "Dashboard is localhost-only; use --host 127.0.0.1 and an SSH tunnel for remote access."
        )
    return host


@click.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address; localhost is the safe default.")
@click.option("--port", default=44678, show_default=True, type=int)
@click.option("--cli-path", default=Config.cli_path, show_default=True)
@click.option("--datadir", default=Config.datadir, show_default=True)
@click.option("--wallet", "wallet_name", default=Config.wallet_name, show_default=True)
@click.option("--service", "service_name", default=Config.service, show_default=True)
def web(host: str, port: int, cli_path: str, datadir: str, wallet_name: str, service_name: str) -> None:
    """Run the local read-only dashboard."""
    host = validate_dashboard_host(host)
    import uvicorn

    from ghostnode.web import create_app

    uvicorn.run(create_app(Config(cli_path=cli_path, datadir=datadir, wallet_name=wallet_name,
                                 service=service_name)), host=host, port=port)
