from __future__ import annotations

from pathlib import Path


def current_identity() -> tuple[int, int | None, str | None]:
    pid = __import__("os").getpid()
    state, ticks, boot_id = process_identity(pid)
    return pid, ticks if state == "ACTIVE" else None, boot_id


def process_identity(pid: int | None) -> tuple[str, int | None, str | None]:
    """Return ACTIVE/DEAD/UNKNOWN without treating inaccessible /proc as dead."""
    if not isinstance(pid, int) or pid <= 0:
        return "UNKNOWN", None, None
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
        end = raw.rfind(")")
        fields = raw[end + 2:].split()
        if len(fields) <= 19:
            return "UNKNOWN", None, None
        ticks = int(fields[19])
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if not boot_id:
            return "UNKNOWN", None, None
        return "ACTIVE", ticks, boot_id
    except FileNotFoundError:
        return "DEAD", None, None
    except (PermissionError, OSError, ValueError):
        return "UNKNOWN", None, None
