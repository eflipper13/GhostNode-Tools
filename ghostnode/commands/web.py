import click
from pathlib import Path

from ghostnode.config import Config
from ghostnode.host import detect_lan_host  # retained for API/test compatibility; explicit host is used
from ghostnode.network import (LAN_MODE, LOCALHOST, NetworkSettings, ports_available,
                               load_network_settings, read_dashboard_token,
                               validate_network_settings)


def validate_dashboard_host(host: str) -> str:
    """Allow only the loopback IPv4 bind in the public v0.1 dashboard."""
    if host != "127.0.0.1":
        raise click.ClickException(
            "The primary dashboard host must be 127.0.0.1; use --network-mode localhost_lan with an explicit assigned LAN address for authenticated dual access."
        )
    return host


@click.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address; localhost is the safe default.")
@click.option("--port", default=44678, show_default=True, type=int)
@click.option("--network-mode", type=click.Choice(["localhost", "localhost_lan"]), default=None,
              help="Use localhost only or localhost plus one LAN IPv4 listener.")
@click.option("--lan-auth-mode", type=click.Choice(["token_required", "trusted_lan"]), default=None,
              help="LAN authentication mode; token_required is the safe default.")
@click.option("--lan-address", default=None, help="Explicit assigned private LAN IPv4 address.")
@click.option("--token-file", default=None, help="Private file containing the LAN bearer token.")
@click.option("--cli-path", default=Config.cli_path, show_default=True)
@click.option("--datadir", default=Config.datadir, show_default=True)
@click.option("--wallet", "wallet_name", default=Config.wallet_name, show_default=True)
@click.option("--service", "service_name", default=Config.service, show_default=True)
def web(host: str, port: int, network_mode: str | None, lan_auth_mode: str | None, lan_address: str | None,
        token_file: str | None, cli_path: str, datadir: str, wallet_name: str,
        service_name: str) -> None:
    """Run the read-only dashboard with an explicit localhost or authenticated LAN mode."""
    host = validate_dashboard_host(host)
    import uvicorn

    from ghostnode.web import create_app

    active_config = Config(cli_path=cli_path, datadir=datadir, wallet_name=wallet_name,
                           service=service_name, dashboard_mode=network_mode or Config.dashboard_mode,
                           dashboard_lan_address=lan_address or Config.dashboard_lan_address,
                           dashboard_port=port, dashboard_token_file=token_file or Config.dashboard_token_file,
                           dashboard_lan_auth_mode=lan_auth_mode or Config.dashboard_lan_auth_mode)
    settings = NetworkSettings(active_config.dashboard_mode, active_config.dashboard_lan_address, port,
                               active_config.dashboard_lan_auth_mode)
    if network_mode is None and lan_address is None and port == 44678 \
            and active_config.dashboard_mode == "localhost" \
            and active_config.dashboard_lan_address is None:
        persisted_path = Path(active_config.dashboard_network_config or "~/.config/ghostnode-tools/network.json").expanduser()
        if persisted_path.exists():
            settings = load_network_settings(persisted_path)
    settings = validate_network_settings(settings)
    if not ports_available(settings):
        raise click.ClickException("one or more dashboard listeners are unavailable; no configuration was changed")
    token = read_dashboard_token(active_config.dashboard_token_file)
    if settings.mode == LAN_MODE and settings.lan_auth_mode == "token_required" and not token:
        raise click.ClickException("token_required LAN mode requires a private bearer token file; no listener was started")
    app = create_app(active_config, network_settings=settings, dashboard_token=token)
    if settings.mode == "localhost":
        uvicorn.run(app, host=LOCALHOST, port=settings.port)
        return
    _run_dual_dashboard(app, settings)


def _run_dual_dashboard(app, settings: NetworkSettings) -> None:
    """Run two uvicorn listeners in one process and stop both on failure."""
    import threading
    import time
    import uvicorn

    servers = [uvicorn.Server(uvicorn.Config(app, host=address, port=settings.port, log_level="info"))
               for address in settings.bind_addresses]
    threads = [threading.Thread(target=server.run, name=f"dashboard-{address}", daemon=True)
               for server, address in zip(servers, settings.bind_addresses)]
    for thread in threads:
        thread.start()
    try:
        while any(thread.is_alive() for thread in threads):
            time.sleep(0.2)
    finally:
        for server in servers:
            server.should_exit = True
        for thread in threads:
            thread.join(timeout=5)
