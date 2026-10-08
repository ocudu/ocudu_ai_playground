# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Identity of the run that wrote an OCUDU log: its build, from the first line, and its time span."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime

from . import preamble

# Bytes read from the end of a log to find its last timestamp.
_TAIL_BYTES = 64 << 10
_build_re = re.compile(r"Built in (?P<mode>\S+) mode using commit (?P<commit>\S+) on branch (?P<branch>\S+)")


@dataclass(frozen=True)
class LogRun:
    """Build and time span, in epoch seconds, of the run that wrote a log."""

    mode: str
    commit: str
    branch: str
    start: float
    end: float


def log_run(path: str | os.PathLike[str]) -> LogRun | None:
    """The run of a log, or None if its first line is not the build line of an OCUDU application."""
    try:
        with open(path, "rb") as f:
            first = f.readline(4096).decode("utf-8", "replace")
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - _TAIL_BYTES))
            tail = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    m = preamble.match_preamble(first)
    build = _build_re.search(first, m.end()) if m else None
    if build is None:
        return None
    start = _epoch(m.group("timestamp"))
    if start is None:
        return None
    end = start
    for line in reversed(tail):
        last = preamble.match_preamble(line)
        if last and (t := _epoch(last.group("timestamp"))) is not None:
            end = max(start, t)
            break
    return LogRun(build.group("mode"), build.group("commit"), build.group("branch"), start, end)


def same_run(a: LogRun, b: LogRun, slack_s: float = 60.0) -> bool:
    """Whether two logs come from the same run: the same build, with time spans overlapping within slack_s."""
    same_build = (a.mode, a.commit, a.branch) == (b.mode, b.commit, b.branch)
    return same_build and a.start <= b.end + slack_s and b.start <= a.end + slack_s


def _epoch(timestamp: str) -> float | None:
    try:
        return datetime.fromisoformat(timestamp).timestamp()
    except ValueError:
        return None
