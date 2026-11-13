import json

from click.testing import CliRunner

from ghostnode.cli import cli
from ghostnode.collectors import system as system_module
from ghostnode.models.results import Status


def fake_metrics():
    class Memory:
        total, available, used, percent = 8_000, 5_000, 3_000, 37.5

    class Swap:
        total, used, free, percent = 2_000, 500, 1_500, 25.0

    class Disk:
        total, used, free, percent = 100_000, 40_000, 60_000, 40.0

    class Psutil:
        virtual_memory = staticmethod(lambda: Memory())
        swap_memory = staticmethod(lambda: Swap())
        disk_usage = staticmethod(lambda _: Disk())
        boot_time = staticmethod(lambda: 1_000.0)
        cpu_count = staticmethod(lambda logical=True: 4)
        cpu_percent = staticmethod(lambda interval=0.1: 12.5)

    return Psutil


def test_text_output(monkeypatch):
    monkeypatch.setattr(system_module, "psutil", fake_metrics())
    monkeypatch.setattr(system_module.time, "time", lambda: 3_000.0)
    result = CliRunner().invoke(cli, ["system"])
    assert result.exit_code == 0
    assert "Status: OK" in result.output
    assert "Hostname:" in result.output
    assert "12.5" in result.output


def test_json_schema(monkeypatch):
    monkeypatch.setattr(system_module, "psutil", fake_metrics())
    monkeypatch.setattr(system_module.time, "time", lambda: 3_000.0)
    result = CliRunner().invoke(cli, ["system", "--json"])
    payload = json.loads(result.output)
    assert set(payload) == {"status", "data"}
    assert payload["status"] == "OK"
    assert {"hostname", "operating_system", "uptime", "cpu", "memory", "swap", "disk"} <= set(payload["data"])


def test_unavailable_metrics_return_unknown(monkeypatch):
    def fail():
        raise OSError("metrics unavailable")

    monkeypatch.setattr(system_module.psutil, "virtual_memory", fail)
    result = CliRunner().invoke(cli, ["system", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.output)["status"] == Status.UNKNOWN.value


def test_help_and_no_system_mutation(monkeypatch):
    runner = CliRunner()
    help_result = runner.invoke(cli, ["--help"])
    assert help_result.exit_code == 0
    assert "system" in help_result.output
    monkeypatch.setattr(system_module.psutil, "cpu_percent", lambda interval=0.1: 0.0)
    assert runner.invoke(cli, ["system"]).exit_code == 0
