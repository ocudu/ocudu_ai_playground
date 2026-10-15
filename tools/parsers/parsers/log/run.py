# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Identity of the run that wrote an OCUDU log: its build, from the first line, and its time span. And the files of a
run directory: its log, found from a file or directory path.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from . import preamble

# Names of the logs of the OCUDU applications, which share a format, by preference when a directory holds several.
LOG_NAMES = ("gnb.log", "du.log", "cu.log", "cu_cp.log", "cu_up.log")
# Pattern of the names of their configuration files, e.g. ocudu_gnb.yml.
CONFIG_GLOB = "ocudu_*.yml"
# Bytes read from the end of a log to find its last timestamp, first and at most, since the last entry may have a
# long body, e.g. an ASN.1 dump.
_TAIL_BYTES = 64 << 10
_MAX_TAIL_BYTES = 64 << 20
_build_re = re.compile(r"Built in (?P<mode>\S+) mode using commit (?P<commit>\S+) on branch (?P<branch>\S+)")


@dataclass(frozen=True)
class LogRun:
    """Build and time span, in epoch seconds with log times taken as UTC, of the run that wrote a log."""

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
            m = preamble.match_preamble(first)
            build = _build_re.search(first, m.end()) if m else None
            start = preamble.to_epoch(m.group("timestamp")) if build else None
            if start is None:
                return None
            end = _last_time(f)
    except OSError:
        return None
    return LogRun(build.group("mode"), build.group("commit"), build.group("branch"), start, max(start, end or start))


def _last_time(f: BinaryIO) -> float | None:
    """The time of the last entry of an open log, read back from its end in growing tails."""
    size = f.seek(0, os.SEEK_END)
    tail_bytes = _TAIL_BYTES
    while True:
        f.seek(max(0, size - tail_bytes))
        for line in reversed(f.read().decode("utf-8", "replace").splitlines()):
            last = preamble.match_preamble(line)
            if last and (t := preamble.to_epoch(last.group("timestamp"))) is not None:
                return t
        if tail_bytes >= min(size, _MAX_TAIL_BYTES):
            return None
        tail_bytes *= 8


def same_run(a: LogRun, b: LogRun, slack_s: float = 60.0) -> bool:
    """Whether two logs come from the same run: the same build, with time spans overlapping within slack_s."""
    same_build = (a.mode, a.commit, a.branch) == (b.mode, b.commit, b.branch)
    return same_build and a.start <= b.end + slack_s and b.start <= a.end + slack_s



def primary_log_in(run_dir: str | os.PathLike[str]) -> Path | None:
    """The OCUDU application log of a run directory, by the preference of LOG_NAMES, or None."""
    run_dir = Path(run_dir)
    return next((run_dir / n for n in LOG_NAMES if (run_dir / n).is_file()), None)


def resolve_run_dir(path: str | os.PathLike[str]) -> Path:
    """The run directory of a path: the directory of a file, a directory with a log, or the directory of the last log
    under it by path, e.g. the latest run of a component or test directory. Raises FileNotFoundError without one.
    """
    p = Path(path).resolve()
    if p.is_file():
        return p.parent
    if primary_log_in(p) is not None:
        return p
    for name in LOG_NAMES:
        candidates = sorted((d for d in p.rglob(name) if d.is_file()), key=str)
        if candidates:
            return candidates[-1].parent
    raise FileNotFoundError(f"No OCUDU app log ({', '.join(LOG_NAMES)}) found under {p}")


def find_log(path: str | os.PathLike[str]) -> Path:
    """The log of a path: a file itself, whatever its name, else the log of its run directory, see resolve_run_dir()."""
    p = Path(path)
    if p.is_file():
        return p.resolve()
    log = primary_log_in(resolve_run_dir(p))
    if log is None:
        raise FileNotFoundError(f"No OCUDU app log under {p}")
    return log
