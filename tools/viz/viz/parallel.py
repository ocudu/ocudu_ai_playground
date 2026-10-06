# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Parsing of large files in chunks, in a pool of worker processes shared by all the sources."""

from __future__ import annotations

import mmap
import multiprocessing
import os
import re
import threading
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any

# Worker processes of the pool, at most. Beyond this, parsing a metrics-heavy log gets no faster on a 16-core
# machine.
MAX_WORKERS = 12

_pool: ProcessPoolExecutor | None = None
_pool_lock = threading.Lock()


def nof_workers() -> int:
    """Worker processes of the pool, from the CPUs this process may run on."""
    return max(1, min(MAX_WORKERS, len(os.sched_getaffinity(0))))


def get_pool() -> ProcessPoolExecutor | None:
    """Returns the shared pool, started on first use, or None with a single CPU."""
    global _pool
    with _pool_lock:
        if _pool is None and nof_workers() > 1:
            # Forking a multithreaded server can deadlock the child, so workers start from a fork server.
            _pool = ProcessPoolExecutor(nof_workers(), mp_context=multiprocessing.get_context("forkserver"))
        return _pool


def chunk_ranges(path: Path, nof_chunks: int, entry_start: re.Pattern) -> list[tuple[int, int]]:
    """Splits a file into at most nof_chunks byte ranges of about the same size.

    Each range but the first starts at a line matching entry_start, so that entries spanning several lines are not
    split.
    """
    size = path.stat().st_size
    if nof_chunks <= 1 or size == 0:
        return [(0, size)]
    bounds = [0]
    with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        for k in range(1, nof_chunks):
            start = _entry_start_after(mm, max(bounds[-1], size * k // nof_chunks), entry_start)
            if start >= size:
                break
            if start > bounds[-1]:
                bounds.append(start)
    bounds.append(size)
    return list(zip(bounds, bounds[1:]))


def lines_before(path: Path, ranges: list[tuple[int, int]]) -> list[int]:
    """Number of lines of a file before each of its ranges, which follow each other and end at line ends.

    The ranges are counted in the pool, since counting a large file takes about a second.
    """
    counts = [0]
    for count in map_chunks(_count_lines, [(str(path), start, end) for start, end in ranges[:-1]]):
        counts.append(counts[-1] + count)
    return counts


def map_chunks(fn: Callable[..., Any], args: Iterable[tuple]) -> Iterator[Any]:
    """Runs fn on each argument tuple, in the pool when there are several, yielding the results in order.

    Arguments whose worker died run in this process instead, and the pool is replaced for the next calls.
    """
    args = list(args)
    pool = get_pool() if len(args) > 1 else None
    futures = []
    if pool is not None:
        try:
            futures = [pool.submit(fn, *a) for a in args]
        except BrokenProcessPool:
            _discard_pool(pool)
    for i, a in enumerate(args):
        if i < len(futures):
            try:
                yield futures[i].result()
                continue
            except BrokenProcessPool:
                _discard_pool(pool)
        yield fn(*a)


def _count_lines(path: str, start: int, end: int) -> int:
    """Number of line ends in the byte range [start, end) of a file."""
    if end <= start:
        return 0
    with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        return mm[start:end].count(b"\n")


def _discard_pool(pool: ProcessPoolExecutor) -> None:
    """Drops a broken pool, so that the next call starts a new one."""
    global _pool
    with _pool_lock:
        if _pool is pool:
            _pool = None
    pool.shutdown(wait=False, cancel_futures=True)


def _entry_start_after(mm: mmap.mmap, pos: int, entry_start: re.Pattern) -> int:
    """Offset of the first line after pos that matches entry_start, or the file size."""
    size = len(mm)
    while True:
        newline = mm.find(b"\n", pos)
        if newline < 0:
            return size
        pos = newline + 1
        if pos >= size or entry_start.match(mm, pos):
            return pos
