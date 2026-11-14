import json

import httpx
import pytest
from click.testing import CliRunner

from ghostnode.cli import cli
from ghostnode.collectors import network
from ghostnode.commands import network as network_command
from ghostnode.config import Config
from ghostnode.network import (LAN_MODE, LOCALHOST_MODE, TRUSTED_LAN, NetworkSettings,
                               ports_available, save_network_settings,
                               token_is_valid, validate_network_settings)
from ghostnode.web import create_app


def test_network_peer_analysis_masks_addresses(monkeypatch):
    responses = [
        {"connections": 2, "connections_in": 0, "connections_out": 2},
        [{"addr": "203.0.113.10:1234", "id": 7, "version": 70001, "subver": "/GhostCore:0.23.1.0/", "protocolversion": 70001, "pingtime": 0.125, "inbound": False, "connection_type": "outbound-full-relay", "network": "ipv4"}],
    ]
    monkeypatch.setattr(network, "_call", lambda method, config: (responses.pop(0), None))
    result = network.collect_network(Config())
    assert result.status.value == "OK"
    assert result.data["connections"]["inbound"] == 0
    assert result.data["connections"]["outbound"] == 2
    assert result.data["peer_count"] == 1
    assert result.data["peers"][0]["ping_time_ms"] == 125.0
    assert result.data["peers"][0]["connection_type"] == "outbound-full-relay"
    assert result.data["ping_summary"] == {"min_ms": 125.0, "avg_ms": 125.0, "max_ms": 125.0}
    assert "203.0.113" not in json.dumps(result.as_dict())


def test_zero_peers_is_warn_not_error(monkeypatch):
    monkeypatch.setattr(network, "_call", lambda method, config: ({"connections": 0} if method == "getnetworkinfo" else [], None))
    result = network.collect_network(Config())
    assert result.status.value == "WARN"
    assert "No connected peers" in result.message


def test_eleven_peers_and_partial_entries(monkeypatch):
    peer = {"id": 1, "addr": "198.51.100.1:1", "version": 70001, "subver": "/GhostCore:0.23.1.0/", "protocolversion": 70001, "pingtime": 0.01, "inbound": False}
    monkeypatch.setattr(network, "_call", lambda method, config: (({"connections": 11, "connections_in": 0, "connections_out": 11}, None) if method == "getnetworkinfo" else ([peer] * 11, None)))
    result = network.collect_network(Config())
    assert result.status.value == "OK"
    assert result.data["peer_count"] == 11
    assert len(result.data["peers"]) == 11

    monkeypatch.setattr(network, "_call", lambda method, config: (({"connections": 1}, None) if method == "getnetworkinfo" else ([peer, "invalid"], None)))
    result = network.collect_network(Config())
    assert result.status.value == "WARN"
    assert result.data["peer_count"] == 1


def test_network_partial_failure(monkeypatch):
    monkeypatch.setattr(network, "_call", lambda method, config: (({"connections": 1}, None) if method == "getnetworkinfo" else (None, "RPC request timed out")))
    result = network.collect_network(Config())
    assert result.status.value == "WARN"
    assert result.data["connections"]["total"] == 1


def test_network_command_json(monkeypatch):
    monkeypatch.setattr(network_command, "collect_network", lambda config: network.Result(network.Status.OK, {"connections": {"total": 1}, "peers": []}))
    result = CliRunner().invoke(cli, ["network", "--json"])
    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["status"] == "OK"


def test_localhost_is_the_safe_default():
    settings = validate_network_settings(NetworkSettings())
    assert settings.mode == LOCALHOST_MODE
    assert settings.bind_addresses == ("127.0.0.1",)


def test_dual_address_requires_assigned_private_ipv4():
    settings = validate_network_settings(NetworkSettings(LAN_MODE, "192.168.1.100", 44678), available=("192.168.1.100",))
    assert settings.bind_addresses == ("127.0.0.1", "192.168.1.100")


@pytest.mark.parametrize("address", ["0.0.0.0", "127.0.0.1", "224.0.0.1", "203.0.113.10", "::1"])
def test_wildcard_loopback_multicast_public_and_ipv6_addresses_are_rejected(address):
    with pytest.raises(ValueError):
        validate_network_settings(NetworkSettings(LAN_MODE, address, 44678), available=())


def test_unassigned_lan_address_is_rejected():
    with pytest.raises(ValueError, match="not assigned"):
        validate_network_settings(NetworkSettings(LAN_MODE, "192.168.1.100", 44678), available=())


def test_port_conflict_detection_is_bounded(monkeypatch):
    class BusySocket:
        def setsockopt(self, *_args): pass
        def bind(self, _address): raise OSError("busy")
        def close(self): pass
    monkeypatch.setattr("ghostnode.network.socket.socket", lambda *_args: BusySocket())
    assert ports_available(NetworkSettings(LOCALHOST_MODE, None, 44678)) is False


def test_network_config_persistence_is_atomic_and_non_secret(tmp_path):
    path = tmp_path / "network.json"
    saved = save_network_settings(NetworkSettings(LOCALHOST_MODE, None, 44679), path)
    assert saved == path
    assert path.stat().st_mode & 0o777 == 0o600
    assert "test-token" not in path.read_text()
    save_network_settings(NetworkSettings(LOCALHOST_MODE, None, 44680), path)
    assert (tmp_path / "network.json.previous").exists()
    assert '44679' in (tmp_path / "network.json.previous").read_text()


def test_token_comparison_is_constant_time_semantically():
    assert token_is_valid("correct", "correct")
    assert not token_is_valid("wrong", "correct")
    assert not token_is_valid(None, "correct")


@pytest.mark.anyio
async def test_lan_dashboard_requires_token_and_allows_authorized_read(monkeypatch):
    monkeypatch.setattr("ghostnode.network.available_lan_ipv4", lambda: ("192.168.1.100",))
    app = create_app(network_settings=NetworkSettings(LAN_MODE, "192.168.1.100", 44678), dashboard_token="test-token")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        denied = await client.get("/api/network/settings")
        allowed = await client.get("/api/network/settings", headers={"Authorization": "Bearer test-token"})
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["data"]["security_status"] == "AUTHENTICATED_LAN"


@pytest.mark.anyio
async def test_trusted_lan_allows_read_only_access_but_protects_admin(monkeypatch):
    monkeypatch.setattr("ghostnode.network.available_lan_ipv4", lambda: ("192.168.1.100",))
    app = create_app(network_settings=NetworkSettings(LAN_MODE, "192.168.1.100", 44678, TRUSTED_LAN),
                     dashboard_token="admin-token")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        settings = await client.get("/api/network/settings")
        proposal_denied = await client.post("/api/network/proposals", json={"mode": "localhost"})
        proposal_allowed = await client.post("/api/network/proposals",
                                             headers={"Authorization": "Bearer admin-token",
                                                      "Origin": "http://192.168.1.100:44678"},
                                             json={"mode": "localhost"})
    assert settings.status_code == 200
    assert settings.json()["data"]["security_status"] == "TRUSTED_LAN"
    assert proposal_denied.status_code == 401
    assert proposal_allowed.status_code == 200


def test_invalid_lan_auth_mode_is_rejected():
    with pytest.raises(ValueError, match="authentication mode"):
        validate_network_settings(NetworkSettings(LAN_MODE, "192.168.1.100", 44678, "unsafe"),
                                  available=("192.168.1.100",))


@pytest.mark.anyio
async def test_network_proposal_does_not_write_or_apply(monkeypatch, tmp_path):
    monkeypatch.setattr("ghostnode.network.available_lan_ipv4", lambda: ("192.168.1.100",))
    app = create_app(network_settings=NetworkSettings(LAN_MODE, "192.168.1.100", 44678), dashboard_token="test-token")
    path = tmp_path / "network.json"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/network/proposals",
                                     headers={"Authorization": "Bearer test-token", "Origin": "http://192.168.1.100:44678"},
                                     json={"mode": "localhost", "port": 44679})
    assert response.status_code == 200
    assert response.json()["data"]["applied"] is False
    assert not path.exists()
