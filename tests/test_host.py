from types import SimpleNamespace
import socket

from click.testing import CliRunner

from ghostnode import host
from ghostnode.commands import web as web_command


def addr(value):
    return SimpleNamespace(family=socket.AF_INET, address=value)


def test_detect_lan_address(monkeypatch):
    monkeypatch.setattr(host.psutil, "net_if_addrs", lambda: {"eth0": [addr("192.0.2.10")], "lo": [addr("127.0.0.1")]})
    result = host.detect_lan_host()
    assert result.address == "192.0.2.10"
    assert result.warning is None


def test_detect_lan_fallback(monkeypatch):
    monkeypatch.setattr(host.psutil, "net_if_addrs", lambda: {"docker0": [addr("172.17.0.1")], "lo": [addr("127.0.0.1")]})
    result = host.detect_lan_host()
    assert result.address == "127.0.0.1"
    assert result.warning


def test_localhost_bind_is_allowed(monkeypatch):
    calls = []
    monkeypatch.setattr(web_command, "detect_lan_host", lambda: (_ for _ in ()).throw(AssertionError("auto detection called")))
    monkeypatch.setattr(web_command, "ports_available", lambda settings: True)
    monkeypatch.setattr(web_command.uvicorn, "run", lambda app, host, port: calls.append((host, port))) if hasattr(web_command, "uvicorn") else None
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: calls.append((host, port)))
    result = CliRunner().invoke(web_command.web, ["--host", "127.0.0.1", "--port", "44678"])
    assert result.exit_code == 0
    assert calls == [("127.0.0.1", 44678)]


def test_public_and_lan_binds_are_rejected():
    runner = CliRunner()
    for address in ("0.0.0.0", "192.168.1.100", "203.0.113.10", "::1"):
        result = runner.invoke(web_command.web, ["--host", address, "--port", "44678"])
        assert result.exit_code != 0
        assert "127.0.0.1" in result.output
