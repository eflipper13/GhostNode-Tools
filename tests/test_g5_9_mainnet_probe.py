import json
import sqlite3

from scripts.g5_9_mainnet_probe import RateLimitedRPC, _output_view, _read_blocks


def test_output_view_redacts_values_addresses_and_scripts():
    view = _output_view({"n": 1, "value": 5, "scriptPubKey": {
        "type": "pubkeyhash", "asm": "secret", "addresses": ["hidden"]}})
    assert view == {"n": 1, "value_present": True, "scriptPubKey_present": True,
                    "script_type": "pubkeyhash", "ownership": None, "output_class": "unknown"}
    assert "secret" not in json.dumps(view)
    assert "hidden" not in json.dumps(view)


def test_read_blocks_uses_sqlite_read_only(tmp_path):
    path = tmp_path / "probe.sqlite3"
    c = sqlite3.connect(path)
    c.execute("create table chain_blocks(network text,is_active int,is_pos int,height int,hash text)")
    c.execute("insert into chain_blocks values('main',1,1,5,'h5')")
    c.commit()
    c.close()
    assert _read_blocks(path, 10) == [{"height": 5, "hash": "h5"}]


def test_rate_limited_rpc_caches_identical_calls(monkeypatch):
    from scripts import g5_9_mainnet_probe as probe
    calls = []
    monkeypatch.setattr(probe, "_call", lambda *args, **kwargs: (calls.append(args) or ({"ok": True}, None)))
    rpc = RateLimitedRPC(probe.Config(cli_path="ghost-cli"), "ghostmain", interval=0)
    assert rpc("getblockchaininfo", None) == rpc("getblockchaininfo", None)
    assert len(calls) == 1
