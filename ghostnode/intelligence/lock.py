from __future__ import annotations

import fcntl
import os
from pathlib import Path


class CollectorLock:
    """Advisory single-writer lock; stale locks disappear when the process exits."""

    def __init__(self, path: str | Path, blocking: bool = False):
        self.path = Path(path)
        self.blocking = blocking
        self._handle = None

    def __enter__(self) -> "CollectorLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+")
        try:
            flags = fcntl.LOCK_EX if self.blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
            fcntl.flock(self._handle.fileno(), flags)
        except BlockingIOError:
            self._handle.close()
            self._handle = None
            raise RuntimeError("another lock holder is active")
        self._handle.seek(0)
        self._handle.truncate()
        self._handle.write(f"{os.getpid()}\n")
        self._handle.flush()
        return self

    def __exit__(self, *_: object) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


class InstanceLock(CollectorLock):
    """Lock held for the lifetime of one runner process."""
