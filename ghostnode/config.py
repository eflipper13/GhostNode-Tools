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
