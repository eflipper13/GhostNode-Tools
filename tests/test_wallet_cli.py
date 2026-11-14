from click.testing import CliRunner

from ghostnode.cli import cli


def test_wallet_setup_json_is_guidance_only():
    result = CliRunner().invoke(cli, ["wallet", "setup", "--json"])
    assert result.exit_code == 0
    assert result.exception is None
    assert "guidance_only" in result.output
    assert "private keys" in result.output
    assert "getnewwallet" not in result.output
    assert "GUIDANCE_AVAILABLE" in result.output
    assert "BACKUP_VERIFIED" in result.output
    assert "passphrase" in result.output.lower()
    assert "recovery" in result.output.lower()


def test_wallet_setup_does_not_create_files(tmp_path):
    datadir = tmp_path / "ghost"
    result = CliRunner().invoke(cli, ["wallet", "setup", "--json", "--datadir", str(datadir)])
    assert result.exit_code == 0
    assert not datadir.exists()


def test_wallet_status_json_is_available():
    result = CliRunner().invoke(cli, ["wallet", "status", "--json"])
    assert result.exit_code in (0, 1)
    assert '"readiness"' in result.output


def test_init_json_command_is_available():
    result = CliRunner().invoke(cli, ["init", "--json", "--datadir", "/tmp/nonexistent-ghostnode-init"])
    assert result.exit_code in (0, 1)
    assert '"mode"' in result.output
    assert '"stages"' in result.output


def test_init_network_plan_is_review_only_by_default(tmp_path):
    result = CliRunner().invoke(cli, ["init", "--json", "--datadir", str(tmp_path / "ghost"),
                                      "--network-mode", "localhost", "--dashboard-port", "44679"])
    assert result.exit_code in (0, 1)
    assert '"applied": false' in result.output
    assert not (tmp_path / "network.json").exists()


def test_init_network_apply_requires_explicit_confirmation(tmp_path):
    path = tmp_path / "network.json"
    result = CliRunner().invoke(cli, ["init", "--json", "--datadir", str(tmp_path / "ghost"),
                                      "--network-config", str(path), "--apply-network"])
    assert result.exit_code != 0
    assert "confirm-network" in result.output
    assert not path.exists()


def test_init_network_apply_writes_only_after_confirmation(tmp_path):
    path = tmp_path / "network.json"
    result = CliRunner().invoke(cli, ["init", "--json", "--datadir", str(tmp_path / "ghost"),
                                      "--network-config", str(path), "--apply-network", "--confirm-network"])
    assert result.exit_code in (0, 1)
    assert path.exists()
    assert '"applied": true' in result.output
