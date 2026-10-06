# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Pool of worker processes shared by all the sources, to parse large files in chunks."""

from __future__ import annotations

import multiprocessing
import os
import threading
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
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


def _discard_pool(pool: ProcessPoolExecutor) -> None:
    """Drops a broken pool, so that the next call starts a new one."""
    global _pool
    with _pool_lock:
        if _pool is pool:
            _pool = None
    pool.shutdown(wait=False, cancel_futures=True)
