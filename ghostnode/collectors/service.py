import subprocess
from typing import Any

from ghostnode.config import Config
from ghostnode.models.results import Result, Status


def collect_service(config: Config) -> Result:
    try:
        completed = subprocess.run(
            ["systemctl", "show", "--no-pager", "--property=ActiveState,SubState", config.service],
            capture_output=True,
            text=True,
            timeout=config.timeout,
            check=False,
        )
    except (FileNotFoundError, PermissionError, OSError):
        return Result(Status.UNKNOWN, {"service": config.service}, "systemd is unavailable")
    except subprocess.TimeoutExpired:
        return Result(Status.UNKNOWN, {"service": config.service}, "systemd query timed out")
    if completed.returncode != 0:
        return Result(Status.UNKNOWN, {"service": config.service}, "systemd state is unavailable")
    values: dict[str, Any] = {"service": config.service}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"ActiveState", "SubState"}:
            values[key[0].lower() + key[1:]] = value
    if "activeState" not in values:
        return Result(Status.UNKNOWN, values, "systemd returned no service state")
    state = values["activeState"]
    return Result(Status.OK if state == "active" else Status.WARN, values)
