"""Reject tracked runtime data and local configuration artifacts."""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import PurePosixPath
from typing import Iterable


APPROVED_DEPENDENCY_LOCKFILES = {"requirements.lock"}


def forbidden_paths(paths: Iterable[str]) -> list[str]:
    """Return tracked paths that must not be part of the source repository."""
    rejected: list[str] = []
    for path in paths:
        name = PurePosixPath(path).name
        if name in APPROVED_DEPENDENCY_LOCKFILES:
            continue
        if (
            fnmatch.fnmatch(name, "*.sqlite*")
            or fnmatch.fnmatch(name, "*.db")
            or fnmatch.fnmatch(name, "*.lock")
            or name == ".env"
            or (name.startswith(".env.") and name != ".env.example")
        ):
            rejected.append(path)
    return sorted(rejected)


def tracked_paths() -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"])
    return [path for path in output.decode().split("\0") if path]


def main() -> int:
    rejected = forbidden_paths(tracked_paths())
    if rejected:
        print("Forbidden tracked local artifacts:", file=sys.stderr)
        print("\n".join(rejected), file=sys.stderr)
        return 1
    print("Tracked artifact policy: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
