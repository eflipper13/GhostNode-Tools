from typing import Any

from ghostnode.collectors.rpc import _call
from ghostnode.config import Config
from ghostnode.models.results import Result, Status


def _peer(peer: dict[str, Any]) -> dict[str, Any]:
    """Keep diagnostics useful without exposing peer addresses or identifiers."""
    return {
        "version": peer.get("version"),
        "subversion": peer.get("subver"),
        "protocol_version": peer.get("protocolversion"),
        "ping_time_ms": round(float(peer["pingtime"]) * 1000, 2) if isinstance(peer.get("pingtime"), (int, float)) else None,
        "inbound": peer.get("inbound"),
        "connection_type": peer.get("connection_type"),
        "network": peer.get("network"),
    }


def collect_network(config: Config) -> Result:
    network, network_error = _call("getnetworkinfo", config)
    peers, peers_error = _call("getpeerinfo", config)
    data: dict[str, Any] = {
        "connections": {
            "total": network.get("connections") if isinstance(network, dict) else None,
            "inbound": network.get("connections_in") if isinstance(network, dict) else None,
            "outbound": network.get("connections_out") if isinstance(network, dict) else None,
        },
        "peers": [],
        "peer_count": len(peers) if isinstance(peers, list) else None,
    }
    valid_peers = [peer for peer in peers if isinstance(peer, dict)] if isinstance(peers, list) else []
    data["peer_count"] = len(valid_peers)
    if isinstance(peers, list):
        data["peers"] = [_peer(peer) for peer in valid_peers]
        pings = [peer["ping_time_ms"] for peer in data["peers"] if isinstance(peer.get("ping_time_ms"), (int, float))]
        protocols = sorted({peer["protocol_version"] for peer in data["peers"] if peer.get("protocol_version") is not None})
        data["ping_summary"] = {
            "min_ms": round(min(pings), 2) if pings else None,
            "avg_ms": round(sum(pings) / len(pings), 2) if pings else None,
            "max_ms": round(max(pings), 2) if pings else None,
        }
        data["protocol_versions"] = protocols
    errors = [error for error in (network_error, peers_error) if error]
    if errors:
        status = Status.ERROR if network is None and peers is None else Status.WARN
        return Result(status, data, "; ".join(errors))
    if not isinstance(peers, list):
        return Result(Status.WARN, data, "RPC returned an unexpected peer list")
    if len(valid_peers) < len(peers):
        return Result(Status.WARN, data, "RPC returned partially invalid peer data")
    if data["peer_count"] == 0:
        return Result(Status.WARN, data, "No connected peers")
    return Result(Status.OK, data)
