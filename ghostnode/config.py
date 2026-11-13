from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    cli_path: str = os.environ.get("GHOSTNODE_CLI_PATH", "ghost-cli")
    datadir: str = os.environ.get("GHOSTNODE_DATADIR", "~/.ghost")
    service: str = os.environ.get("GHOSTNODE_SERVICE", "ghost.service")
    timeout: float = 5.0
