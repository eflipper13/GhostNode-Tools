from click.testing import CliRunner

from ghostnode.cli import cli


def test_wallet_setup_json_is_guidance_only():
    result = CliRunner().invoke(cli, ["wallet", "setup", "--json"])
    assert result.exit_code == 0
    assert result.exception is None
    assert "guidance_only" in result.output
    assert "private keys" in result.output
    assert "getnewwallet" not in result.output


def test_wallet_status_json_is_available():
    result = CliRunner().invoke(cli, ["wallet", "status", "--json"])
    assert result.exit_code in (0, 1)
    assert '"readiness"' in result.output
