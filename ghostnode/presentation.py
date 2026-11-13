"""Pure presentation helpers for dashboard data."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def format_block_time(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "N/A"
    try:
        return datetime.fromtimestamp(value, timezone.utc).astimezone(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return "N/A"


def short_hash(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "N/A"
    return value if len(value) <= 13 else f"{value[:8]}...{value[-5:]}"


def active_label(value: object) -> str:
    return "Active" if value == 1 else "Inactive" if value == 0 else "Unknown"


def pos_label(value: object) -> str:
    return "PoS" if value == 1 else "PoW" if value == 0 else "Unknown"
