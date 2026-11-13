import ipaddress
import socket
from dataclasses import dataclass

import psutil


_VIRTUAL_PREFIXES = ("docker", "br-", "virbr", "veth", "tun", "tap", "wg", "tailscale", "zt")


@dataclass(frozen=True)
class HostAddress:
    address: str
    warning: str | None = None


def detect_lan_host() -> HostAddress:
    """Select one physical-looking global IPv4 address without network calls."""
    candidates: list[tuple[str, str]] = []
    for interface, addresses in psutil.net_if_addrs().items():
        name = interface.lower()
        if name == "lo" or name.startswith(_VIRTUAL_PREFIXES):
            continue
        for address in addresses:
            if address.family != socket.AF_INET:
                continue
            try:
                ip = ipaddress.ip_address(address.address)
            except ValueError:
                continue
            if ip.is_loopback or ip.is_link_local or ip.is_unspecified:
                continue
            candidates.append((interface, str(ip)))
    private = [item for item in candidates if ipaddress.ip_address(item[1]).is_private]
    selected = private if private else candidates
    if len(selected) == 1:
        return HostAddress(selected[0][1])
    if not selected:
        return HostAddress("127.0.0.1", "No suitable LAN IPv4 address found; using localhost")
    return HostAddress("127.0.0.1", "Multiple LAN IPv4 addresses found; using localhost")
