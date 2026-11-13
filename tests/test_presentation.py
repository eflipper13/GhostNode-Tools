from datetime import datetime, timezone

from ghostnode.presentation import active_label, format_block_time, pos_label, short_hash


def test_block_time_uses_warsaw_and_handles_dst():
    # 2026-01-15 12:00 UTC -> 13:00 CET; 2026-07-15 12:00 UTC -> 14:00 CEST.
    assert format_block_time(datetime(2026, 1, 15, 12, tzinfo=timezone.utc).timestamp()) == "2026-01-15 13:00:00"
    assert format_block_time(datetime(2026, 7, 15, 12, tzinfo=timezone.utc).timestamp()) == "2026-07-15 14:00:00"


def test_unknown_time_and_labels_are_safe():
    assert format_block_time(None) == "N/A"
    assert active_label(1) == "Active"
    assert active_label(0) == "Inactive"
    assert active_label(None) == "Unknown"
    assert pos_label(1) == "PoS"
    assert pos_label(0) == "PoW"
    assert pos_label(None) == "Unknown"


def test_hash_shortening_preserves_full_value_separately():
    value = "2ca5fb50" + "a" * 50 + "7914a"
    assert short_hash(value) == "2ca5fb50...7914a"
    assert short_hash(None) == "N/A"
