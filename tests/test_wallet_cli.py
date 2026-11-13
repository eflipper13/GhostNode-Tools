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
