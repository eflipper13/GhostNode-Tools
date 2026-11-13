from ghostnode.intelligence.diagnostics import sanitize_error


def test_sanitize_error_removes_credentials_cookie_token_and_sensitive_path():
    raw = "rpcpassword=secret cookie=abc token=xyz txid=tx-secret wallet_address=Gsecret /tmp/example/.ghost/wallet.dat"
    safe = sanitize_error(raw)
    assert "secret" not in safe
    assert "abc" not in safe
    assert "xyz" not in safe
    assert "wallet.dat" not in safe
    assert "tx-secret" not in safe
    assert "Gsecret" not in safe


def test_sanitize_error_redacts_standalone_ids_and_addresses():
    safe = sanitize_error("failure " + "a" * 64 + " G" + "A" * 30)
    assert "a" * 64 not in safe
    assert "G" + "A" * 30 not in safe
    assert "failure" in safe
    assert "REDACTED" in safe
