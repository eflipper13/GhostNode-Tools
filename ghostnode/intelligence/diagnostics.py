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
    # Redact standalone identifiers and common Ghost address-shaped values
    # that may appear in CLI stderr while retaining the error context.
    text = re.sub(r"\b[0-9a-fA-F]{64}\b", "[REDACTED_ID]", text)
    text = re.sub(r"\bG[A-Za-z0-9]{20,}\b", "[REDACTED_ADDRESS]", text)
    return " ".join(text.split())[:300] or "unspecified error"
