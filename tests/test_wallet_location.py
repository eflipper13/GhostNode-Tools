from pathlib import Path

from ghostnode.config import Config
from ghostnode.wallet_location import detect_wallet_location


def test_standard_legacy_wallet_location_uses_metadata_only(tmp_path):
    datadir = tmp_path / "ghost"
    datadir.mkdir()
    wallet_file = datadir / "wallet.dat"
    wallet_file.write_bytes(b"synthetic marker")
    before = wallet_file.read_bytes()

    result = detect_wallet_location(Config(datadir=str(datadir)))

    assert result["status"] == "WALLET_PATH_FOUND_BY_METADATA"
    assert result["path"] == str(wallet_file)
    assert wallet_file.read_bytes() == before


def test_named_wallet_directory_is_detected_for_custom_datadir(tmp_path):
    datadir = tmp_path / "custom-ghost"
    wallet_dir = datadir / "wallets" / "alice"
    wallet_dir.mkdir(parents=True)

    result = detect_wallet_location(Config(datadir=str(datadir), wallet_name="alice"))

    assert result["status"] == "WALLET_PATH_FOUND_BY_METADATA"
    assert result["path"] == str(wallet_dir)


def test_explicit_custom_wallet_dir_is_supported(tmp_path):
    datadir = tmp_path / "ghost"
    datadir.mkdir()
    wallet_dir = tmp_path / "wallet-storage"
    wallet = wallet_dir / "named"
    wallet.mkdir(parents=True)

    result = detect_wallet_location(Config(datadir=str(datadir), wallet_name="named",
                                           wallet_dir=str(wallet_dir)))

    assert result["status"] == "WALLET_PATH_FOUND_BY_METADATA"
    assert result["path"] == str(wallet)


def test_unknown_location_does_not_guess_wallet_dat(tmp_path):
    datadir = tmp_path / "ghost"
    datadir.mkdir()

    result = detect_wallet_location(Config(datadir=str(datadir)))

    assert result["status"] == "WALLET_PATH_UNKNOWN"
    assert result["path"] is None


def test_remote_rpc_hides_remote_filesystem_path(tmp_path):
    result = detect_wallet_location(Config(datadir=str(tmp_path), rpc_host="node.example", rpc_port=51725))
    assert result == {
        "status": "WALLET_PATH_UNKNOWN",
        "scope": "remote",
        "path": None,
        "message": "The wallet is on a remote RPC node; its filesystem path is not exposed or inspected.",
    }


def test_unsupported_wallet_file_format_is_unknown(tmp_path):
    datadir = tmp_path / "ghost"
    unsupported = datadir / "wallets" / "ghostmain"
    unsupported.parent.mkdir(parents=True)
    unsupported.write_text("not a wallet directory")

    result = detect_wallet_location(Config(datadir=str(datadir)))
    assert result["status"] == "WALLET_PATH_UNKNOWN"
    assert result["path"] is None
