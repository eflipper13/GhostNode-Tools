from scripts.g5_9_d_wallet_audit import _shape, _utxo_view


def test_shape_redacts_sensitive_wallet_fields_and_values():
    shaped = _shape({"address": "secret", "txid": "secret", "amount": 1.25,
                     "ismine": True, "nested": {"scriptPubKey": "secret"}})
    assert "secret" not in str(shaped)
    assert shaped["amount"] == "float"
    assert shaped["ismine"] == "bool"


def test_shape_preserves_collection_counts_without_contents():
    assert _shape([{"txid": "secret"}, {"category": "stake"}]) == {"count": 2, "item_types": ["dict"]}


def test_utxo_view_reports_counts_and_redacts_identity():
    report = _utxo_view([{"txid": "secret", "vout": 2, "confirmations": 9,
                          "amount": 1, "stakeable": True, "spendable": False}])
    assert report["count"] == 1
    assert report["stakeable_true"] == 1
    assert report["items"][0]["txid_present"] is True
    assert "secret" not in str(report)
