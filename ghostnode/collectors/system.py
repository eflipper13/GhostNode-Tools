import datetime as dt
import os
import platform
import socket
import time
from typing import Any

import psutil

from ghostnode.models.results import Result, Status


def _bytes(value: int | float) -> dict[str, Any]:
    return {"bytes": int(value)}


def collect_system() -> Result:
    """Collect read-only host metrics and return a stable result schema."""
    try:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        uptime_seconds = max(0, int(time.time() - psutil.boot_time()))
        data = {
            "hostname": socket.gethostname(),
            "operating_system": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
            },
            "uptime": {
                "seconds": uptime_seconds,
                "human": str(dt.timedelta(seconds=uptime_seconds)),
            },
            "cpu": {
                "cores": psutil.cpu_count(logical=True),
                "usage_percent": psutil.cpu_percent(interval=0.1),
            },
            "memory": {
                "total": _bytes(memory.total),
                "available": _bytes(memory.available),
                "used": _bytes(memory.used),
                "usage_percent": memory.percent,
            },
            "swap": {
                "total": _bytes(swap.total),
                "used": _bytes(swap.used),
                "free": _bytes(swap.free),
                "usage_percent": swap.percent,
            },
            "disk": {
                "path": os.path.abspath(os.sep),
                "total": _bytes(disk.total),
                "used": _bytes(disk.used),
                "free": _bytes(disk.free),
                "usage_percent": disk.percent,
            },
        }
        return Result(Status.OK, data)
    except (OSError, RuntimeError, ValueError) as exc:
        return Result(Status.UNKNOWN, {}, f"Unable to collect system metrics: {exc}")
