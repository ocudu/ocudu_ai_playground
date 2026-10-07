# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from viz import parallel
from viz.sources import log_metrics
from viz.sources.log_metrics import LogMetricsSource
from viz.store import StoreCache

from .helpers import write_log


def double_or_die(x):
    """Doubles x in this process, and kills the worker process it runs in."""
    if multiprocessing.parent_process() is not None:
        os._exit(1)
    return 2 * x


def dump(store):
    """Contents of the dataset tables and metadata of a store, ignoring the record offsets."""
    with closing(sqlite3.connect(store._uri, uri=True)) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'ds_%' ORDER BY name")]
        rows = {t: conn.execute(f'SELECT * FROM "{t}" ORDER BY _rec').fetchall() for t in tables}
        columns = {t: [c[1] for c in conn.execute(f'PRAGMA table_info("{t}")')] for t in tables}
        datasets = conn.execute("SELECT * FROM datasets ORDER BY name").fetchall()
    meta = {k: v for k, v in store.meta.items() if k != "path"}
    return rows, columns, datasets, meta


class ParallelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = write_log(self.dir / "gnb.log", nof_seconds=300, nof_ues=4, executors=True, events=True)

    def tearDown(self):
        self.tmp.cleanup()

    def open(self, name, jobs, chunk_size):
        with mock.patch.object(parallel, "_jobs", jobs), mock.patch.object(log_metrics, "_MIN_CHUNK_SIZE", chunk_size):
            return StoreCache(self.dir / name).open(self.log, LogMetricsSource())

    def test_chunks_give_the_same_store(self):
        serial = self.open("serial", 1, 4096)
        chunked = self.open("chunked", None, 4096)
        self.assertEqual(dump(chunked), dump(serial))
        nof_lines = len(self.log.read_text().splitlines())
        for record in (1, 2, 999, 1000, 1001, nof_lines // 2, nof_lines):
            self.assertEqual(chunked.records(around=record, count=5), serial.records(around=record, count=5))


    @unittest.skipIf(parallel.nof_workers() < 2, "needs several CPUs")
    def test_dead_workers_fall_back_to_this_process(self):
        first = parallel.get_pool()
        self.assertEqual(list(parallel.map_chunks(double_or_die, [(1,), (2,), (3,)])), [2, 4, 6])
        self.assertIsNot(parallel.get_pool(), first)

    @unittest.skipIf(parallel.nof_workers() < 2, "needs several CPUs")
    def test_shutdown_stops_the_workers(self):
        pool = parallel.get_pool()
        self.assertEqual(list(parallel.map_chunks(abs, [(-1,), (-2,)])), [1, 2])
        workers = list(pool._processes.values())
        parallel.shutdown()
        self.assertFalse(any(w.is_alive() for w in workers))
        self.assertIsNot(parallel.get_pool(), pool)


if __name__ == "__main__":
    unittest.main()
