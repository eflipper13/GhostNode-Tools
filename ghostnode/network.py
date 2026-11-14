"""Validated dashboard network settings and private configuration helpers."""

from __future__ import annotations

import ipaddress
import json
import os
import secrets
import shutil
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psutil

LOCALHOST = "127.0.0.1"
LOCALHOST_MODE = "localhost"
LAN_MODE = "localhost_lan"
DEFAULT_PORT = 44678


@dataclass(frozen=True)
class NetworkSettings:
    mode: str = LOCALHOST_MODE
    lan_address: str | None = None
    port: int = DEFAULT_PORT

    @property
    def bind_addresses(self) -> tuple[str, ...]:
        return (LOCALHOST,) if self.mode == LOCALHOST_MODE else (LOCALHOST, self.lan_address or "")

    def as_dict(self) -> dict[str, object]:
        return {"mode": self.mode, "lan_address": self.lan_address, "port": self.port,
                "localhost_address": LOCALHOST, "bind_addresses": list(self.bind_addresses)}


def available_lan_ipv4() -> tuple[str, ...]:
    """Return non-loopback IPv4 addresses currently assigned to real interfaces."""
    result: list[str] = []
    virtual_prefixes = ("docker", "br-", "virbr", "veth", "tun", "tap", "wg", "tailscale", "zt")
    for interface, addresses in psutil.net_if_addrs().items():
        if interface.lower() == "lo" or interface.lower().startswith(virtual_prefixes):
            continue
        for address in addresses:
            if address.family != socket.AF_INET:
                continue
            try:
                value = ipaddress.ip_address(address.address)
            except ValueError:
                continue
            if value.version == 4 and value.is_private and not value.is_loopback and not value.is_unspecified \
                    and not value.is_multicast and not value.is_link_local:
                if str(value) not in result:
                    result.append(str(value))
    return tuple(sorted(result))


def validate_network_settings(settings: NetworkSettings,
                              available: Iterable[str] | None = None) -> NetworkSettings:
    if settings.mode not in {LOCALHOST_MODE, LAN_MODE}:
        raise ValueError("unsupported dashboard network mode")
    if not isinstance(settings.port, int) or isinstance(settings.port, bool) or not 1 <= settings.port <= 65535:
        raise ValueError("dashboard port must be between 1 and 65535")
    if settings.port < 1024:
        raise ValueError("dashboard port must be unprivileged")
    if settings.mode == LOCALHOST_MODE:
        if settings.lan_address not in (None, ""):
            raise ValueError("localhost mode cannot configure a LAN address")
        return NetworkSettings(LOCALHOST_MODE, None, settings.port)
    try:
        address = ipaddress.ip_address(settings.lan_address or "")
    except ValueError as exc:
        raise ValueError("LAN address must be an IPv4 address") from exc
    if address.version != 4 or address.is_loopback or address.is_unspecified or address.is_multicast \
            or address.is_link_local or not address.is_private:
        raise ValueError("LAN address must be a private, non-loopback IPv4 address")
    assigned = set(available if available is not None else available_lan_ipv4())
    if str(address) not in assigned:
        raise ValueError("LAN address is not assigned to a local interface")
    return NetworkSettings(LAN_MODE, str(address), settings.port)


def load_network_settings(path: str | Path | None = None) -> NetworkSettings:
    target = Path(path or os.environ.get("GHOSTNODE_NETWORK_CONFIG", "~/.config/ghostnode-tools/network.json")).expanduser()
    if not target.exists():
        return NetworkSettings()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return validate_network_settings(NetworkSettings(data.get("mode", LOCALHOST_MODE),
                                                         data.get("lan_address"),
                                                         int(data.get("port", DEFAULT_PORT))))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return NetworkSettings()


def save_network_settings(settings: NetworkSettings, path: str | Path | None = None) -> Path:
    """Atomically persist validated non-secret settings and return the path."""
    checked = validate_network_settings(settings)
    target = Path(path or os.environ.get("GHOSTNODE_NETWORK_CONFIG", "~/.config/ghostnode-tools/network.json")).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    previous = target.with_name(f"{target.name}.previous")
    if target.exists():
        shutil.copy2(target, previous)
        os.chmod(previous, 0o600)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(checked.as_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def ports_available(settings: NetworkSettings) -> bool:
    """Check all requested binds without changing any system configuration."""
    sockets: list[socket.socket] = []
    try:
        for address in settings.bind_addresses:
            if not address:
                return False
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((address, settings.port))
            except OSError:
                sock.close()
                return False
            sockets.append(sock)
        return True
    finally:
        for sock in sockets:
            sock.close()


def read_dashboard_token(token_file: str | Path | None = None) -> str | None:
    path = token_file or os.environ.get("GHOSTNODE_DASHBOARD_TOKEN_FILE")
    if path:
        try:
            token = Path(path).expanduser().read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
    else:
        token = os.environ.get("GHOSTNODE_DASHBOARD_TOKEN", "").strip()
    return token or None


def token_is_valid(provided: str | None, expected: str | None) -> bool:
    return bool(provided and expected and secrets.compare_digest(provided, expected))
