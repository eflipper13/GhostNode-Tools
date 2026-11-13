import os
import subprocess
from pathlib import Path


def test_schema_probe_redacts_scalars_and_reports_shapes(tmp_path):
    cli = tmp_path / "ghost-cli"
    cli.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$2\" in\n"
        "  getblock) echo '{\"hash\":\"secret-hash\",\"height\":1,\"tx\":[{\"txid\":\"secret-tx\",\"vout\":[],\"ok\":true}]}' ;;\n"
        "  gettxout) echo 'null' ;;\n"
        "  getblockreward) echo 'Requires -txindex enabled' >&2; exit 1 ;;\n"
        "  *) echo '{}';;\n"
        "esac\n"
    )
    cli.chmod(0o700)
    script = Path(__file__).parents[1] / "scripts/g5735a-rpc-schema.sh"
    syntax = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
    result = subprocess.run(
        ["bash", str(script)],
        env={**os.environ, "GHOSTNODE_CLI_PATH": str(cli), "GHOSTNODE_DATADIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "response: OBJECT" in result.stdout
    assert "secret-hash" not in result.stdout
    assert "secret-tx" not in result.stdout
    assert "INDEX_REQUIRED" in result.stdout
    assert "response: NULL" in result.stdout


def test_schema_probe_classifies_address_txout_and_all_vouts(tmp_path):
    cli = tmp_path / "ghost-cli"
    cli.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$2\" in\n"
        "  getaddressinfo) echo '{\"ismine\":true,\"solvable\":false,\"iswatchonly\":null,\"ischange\":true}' ;;\n"
        "  gettxout) echo '{}' ;;\n"
        "  getrawtransaction) if [[ \"$4\" == 0 ]]; then echo 'aabb'; else echo '{\"txid\":\"hidden\"}'; fi ;;\n"
        "  getblock) echo '{\"tx\":[{\"vout\":[{\"n\":0,\"type\":\"data\"},{\"n\":1,\"value\":1,\"scriptPubKey\":{\"asm\":\"hidden\",\"addresses\":[],\"stakeaddresses\":[]}}]}]}' ;;\n"
        "  *) echo '{}' ;;\n"
        "esac\n"
    )
    cli.chmod(0o700)
    script = Path(__file__).parents[1] / "scripts/g5735a-rpc-schema.sh"
    result = subprocess.run(
        ["bash", str(script)],
        env={**os.environ, "GHOSTNODE_CLI_PATH": str(cli), "GHOSTNODE_DATADIR": str(tmp_path),
             "GHOSTNODE_OWN_ADDRESS": "own", "GHOSTNODE_FOREIGN_ADDRESS": "foreign"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "ismine: TRUE" in result.stdout
    assert "solvable: FALSE" in result.stdout
    assert "iswatchonly: NULL" in result.stdout
    assert "response: OBJECT" in result.stdout
    assert "response: RAW_HEX" in result.stdout
    assert "vout[0]: n=0" in result.stdout
    assert "vout[1]: n=1" in result.stdout
    assert "hidden" not in result.stdout
