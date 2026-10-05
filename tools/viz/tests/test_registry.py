# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import tempfile
import time
import unittest
from pathlib import Path

from viz.files import PathNotAllowed
from viz.registry import OpenError, SourceRegistry
from viz.sources.log_metrics import LogMetricsSource
from viz.store import StoreCache

from .helpers import write_log


def wait_ready(registry, source_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = registry.entries()[source_id]
        if entry.status != "parsing":
            return entry
        time.sleep(0.02)
    raise AssertionError("parsing did not finish")


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name).resolve()
        self.log = write_log(self.dir / "gnb.log")
        self.registry = SourceRegistry(StoreCache(self.dir / "cache"), [LogMetricsSource()], [self.dir])

    def tearDown(self):
        # Background parsing must finish before its cache directory is removed.
        for entry in self.registry.entries():
            wait_ready(self.registry, entry.id)
        self.tmp.cleanup()

    def test_open_parses_in_background(self):
        entry = self.registry.open(self.log)
        self.assertEqual(entry.id, 0)
        entry = wait_ready(self.registry, 0)
        self.assertEqual((entry.status, entry.progress), ("ready", 1.0))
        self.assertIn("sched_ue", self.registry.get_ready(0).datasets)

    def test_open_same_file_twice(self):
        first = self.registry.open(self.log)
        second = self.registry.open(str(self.dir / "." / "gnb.log"))
        self.assertIs(first, second)
        self.assertEqual(len(self.registry.entries()), 1)

    def test_open_errors(self):
        (self.dir / "data.bin").write_bytes(b"\0\1\2")
        with self.assertRaisesRegex(OpenError, "unsupported"):
            self.registry.open(self.dir / "data.bin")
        with self.assertRaisesRegex(OpenError, "not a file"):
            self.registry.open(self.dir)
        with self.assertRaises(PathNotAllowed):
            self.registry.open("/etc/hostname")
        with self.assertRaisesRegex(OpenError, "not available"):
            SourceRegistry().open(self.log)

    def test_close_and_reopen(self):
        self.registry.open(self.log)
        wait_ready(self.registry, 0)
        self.registry.close(0)
        entry = self.registry.entries()[0]
        self.assertEqual((entry.status, entry.store), ("closed", None))
        self.assertIsNone(self.registry.get_ready(0))
        reopened = self.registry.open(self.log)
        self.assertEqual(reopened.id, 1)
        with self.assertRaises(KeyError):
            self.registry.close(7)

    def test_unknown_and_unparsed_sources(self):
        with self.assertRaises(KeyError):
            self.registry.get_ready(3)


if __name__ == "__main__":
    unittest.main()
