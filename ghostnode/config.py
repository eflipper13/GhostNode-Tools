from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    cli_path: str = os.environ.get("GHOSTNODE_CLI_PATH", "ghost-cli")
    datadir: str = os.environ.get("GHOSTNODE_DATADIR", "~/.ghost")
    service: str = os.environ.get("GHOSTNODE_SERVICE", "ghost.service")
    timeout: float = 5.0
    rpc_host: str | None = os.environ.get("GHOSTNODE_RPC_HOST") or None
    rpc_port: int | None = (int(os.environ["GHOSTNODE_RPC_PORT"])
                            if os.environ.get("GHOSTNODE_RPC_PORT") else None)
    wallet_name: str = os.environ.get("GHOSTNODE_WALLET", "ghostmain")
    wallet_dir: str | None = os.environ.get("GHOSTNODE_WALLET_DIR") or None
    dashboard_mode: str = os.environ.get("GHOSTNODE_DASHBOARD_MODE", "localhost")
    dashboard_lan_address: str | None = os.environ.get("GHOSTNODE_DASHBOARD_LAN_ADDRESS") or None
    dashboard_port: int = (int(os.environ["GHOSTNODE_DASHBOARD_PORT"])
                            if os.environ.get("GHOSTNODE_DASHBOARD_PORT") else 44678)
    dashboard_token_file: str | None = os.environ.get("GHOSTNODE_DASHBOARD_TOKEN_FILE") or None
    dashboard_lan_auth_mode: str = os.environ.get("GHOSTNODE_DASHBOARD_LAN_AUTH_MODE", "token_required")
    dashboard_network_config: str | None = os.environ.get("GHOSTNODE_NETWORK_CONFIG") or None
