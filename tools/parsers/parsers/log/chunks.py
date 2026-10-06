# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Splitting of OCUDU logs into byte ranges that can be parsed independently, e.g. by parallel workers.

Ranges start at log entries, so that entries spanning several lines are never split, and line numbers can be
continued across ranges from their line counts.
"""

from __future__ import annotations

import itertools
import mmap
import re
from concurrent.futures import Executor
from pathlib import Path

from .events import ENTRY_START_PATTERN

# Start of the lines that begin a log entry, as a bytes pattern.
ENTRY_START_RE = re.compile(ENTRY_START_PATTERN.encode())


def chunk_ranges(path: str | Path, nof_chunks: int) -> list[tuple[int, int]]:
    """Splits a log into at most nof_chunks byte ranges [start, end) of about the same size.

    The ranges follow each other, and each one but the first starts at a line that begins a log entry.
    """
    path = Path(path)
    size = path.stat().st_size
    if nof_chunks <= 1 or size == 0:
        return [(0, size)]
    bounds = [0]
    with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        for k in range(1, nof_chunks):
            start = _entry_start_after(mm, max(bounds[-1], size * k // nof_chunks))
            if start >= size:
                break
            if start > bounds[-1]:
                bounds.append(start)
    bounds.append(size)
    return list(zip(bounds, bounds[1:]))


def count_lines(path: str | Path, start: int, end: int) -> int:
    """Number of line ends in the byte range [start, end) of a file."""
    if end <= start:
        return 0
    with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        return mm[start:end].count(b"\n")


def first_lines(path: str | Path, ranges: list[tuple[int, int]], executor: Executor | None = None) -> list[int]:
    """Line number, from 1, of the first line of each range of chunk_ranges(), counting in executor if given."""
    args = [(str(path), start, end) for start, end in ranges[:-1]]
    counts = executor.map(count_lines, *zip(*args)) if executor and args else itertools.starmap(count_lines, args)
    return [1 + n for n in itertools.accumulate(counts, initial=0)]


def read_lines(path: str | Path, start: int, end: int) -> list[bytes]:
    """Lines of the byte range [start, end) of a file, without their line ends."""
    if end <= start:
        return []
    with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        lines = mm[start:end].split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    return lines


def _entry_start_after(mm: mmap.mmap, pos: int) -> int:
    """Offset of the first line after pos that begins a log entry, or the file size."""
    size = len(mm)
    while True:
        newline = mm.find(b"\n", pos)
        if newline < 0:
            return size
        pos = newline + 1
        if pos >= size or ENTRY_START_RE.match(mm, pos):
            return pos
