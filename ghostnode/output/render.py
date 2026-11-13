import json
import re
from typing import Any

from ghostnode.models.results import Result


def render_json(result: Result) -> str:
    return json.dumps(result.as_dict(), indent=2, sort_keys=True)


def _human(value: Any) -> str:
    if isinstance(value, dict) and set(value) == {"bytes"}:
        amount = float(value["bytes"])
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if amount < 1024 or unit == "TiB":
                return f"{amount:.1f} {unit}"
            amount /= 1024
    return str(value)


def _lines(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            label = re.sub(r"(?<!^)([A-Z])", r" \1", key).replace("_", " ").capitalize()
            lines.extend(_lines(item, f"{prefix}{label} "))
        return lines
    return [f"{prefix.rstrip()}: {_human(value)}"]


def render_text(result: Result) -> str:
    lines = [f"Status: {result.status.value}"]
    if result.message:
        lines.append(f"Message: {result.message}")
    for key, value in result.data.items():
        label = key.replace("_", " ").capitalize()
        lines.extend(_lines(value, f"{label} "))
    return "\n".join(lines)
