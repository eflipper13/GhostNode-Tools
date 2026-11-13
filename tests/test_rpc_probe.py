import os
import subprocess
from pathlib import Path


def test_rpc_probe_is_syntax_valid_and_redacts_payloads(tmp_path):
    fake_cli = tmp_path / "ghost-cli"
    fake_cli.write_text("#!/usr/bin/env bash\n" "echo '{\"private\":\"secret\"}'\n")
    fake_cli.chmod(0o700)
    script = Path(__file__).parents[1] / "scripts/g5734-rpc-probe.sh"
    syntax = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
    result = subprocess.run(
        ["bash", str(script)],
        env={**os.environ, "GHOSTNODE_CLI_PATH": str(fake_cli), "GHOSTNODE_DATADIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "SUCCESS" in result.stdout
    assert "secret" not in result.stdout
    assert "private" not in result.stdout


def test_rpc_probe_classifies_common_readonly_errors(tmp_path):
    fake_cli = tmp_path / "ghost-cli"
    fake_cli.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$2\" in\n"
        "  getrawtransaction) echo 'Method not found' >&2; exit 1;;\n"
        "  gettransaction) echo 'Requires -txindex enabled' >&2; exit 1;;\n"
        "  listtransactions) echo 'Wallet file not found' >&2; exit 1;;\n"
        "  *) echo '{}' ;;\n"
        "esac\n"
    )
    fake_cli.chmod(0o700)
    script = Path(__file__).parents[1] / "scripts/g5734-rpc-probe.sh"
    result = subprocess.run(
        ["bash", str(script)],
        env={**os.environ, "GHOSTNODE_CLI_PATH": str(fake_cli), "GHOSTNODE_DATADIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "METHOD_NOT_FOUND" in result.stdout
    assert "INDEX_REQUIRED" in result.stdout
    assert "WALLET_ERROR" in result.stdout
