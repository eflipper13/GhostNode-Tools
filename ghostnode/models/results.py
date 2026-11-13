from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    OK = "OK"
    WARN = "WARN"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass
class Result:
    status: Status
    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"status": self.status.value, "data": self.data}
        if self.message:
            result["message"] = self.message
        return result
