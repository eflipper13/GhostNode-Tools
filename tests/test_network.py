import json

from click.testing import CliRunner

from ghostnode.cli import cli
from ghostnode.collectors import network
from ghostnode.commands import network as network_command
from ghostnode.config import Config


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
