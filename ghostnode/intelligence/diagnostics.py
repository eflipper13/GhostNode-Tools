from __future__ import annotations

import re
from typing import Any


def sanitize_error(error: Any) -> str:
    """Return bounded diagnostics without credentials, wallet data, or secrets."""
    text = str(error)
    text = re.sub(r"(?i)(rpc(?:user|password)|password|cookie|token|secret)\s*[=:]\s*[^\s,;]+",
                  r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)(txid|transaction(?:_id|id)?|wallet[_ -]?address|address)\s*[=:]\s*[^\s,;]+",
                  r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)(/[^\s]*(?:\.ghost|wallet\.dat|\.cookie)[^\s]*)",
                  "[REDACTED_PATH]", text)
    text = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", text)
    return " ".join(text.split())[:300] or "unspecified error"
