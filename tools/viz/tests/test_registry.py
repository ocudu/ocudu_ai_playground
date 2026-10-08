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
    """Waits for the parsing of a source and of its events."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = registry.entries()[source_id]
        busy = entry.status == "parsing" or entry.events_status == "parsing"
        if not busy and not (entry.status == "ready" and entry.events_status == "pending"):
            return entry
        time.sleep(0.02)
    raise AssertionError("parsing did not finish")


class OnRequestLogs(LogMetricsSource):
    """Logs whose name starts with "mac" are parsed only on request, like MAC pcaps."""

    def on_request(self, path):
        return path.name.startswith("mac")


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

    def test_events_parsed_after_datasets(self):
        log = write_log(self.dir / "events.log", events=True)
        entry = wait_ready(self.registry, self.registry.open(log).id)
        self.assertEqual(entry.events_status, "ready")
        self.assertEqual(entry.store.event_counts["ra"], 2)

    def test_add_store_parses_events(self):
        cache = self.registry.cache
        store = cache.open(write_log(self.dir / "events.log", events=True), LogMetricsSource())
        self.assertFalse(store.events_ready)
        entry = wait_ready(self.registry, self.registry.add_store(store, LogMetricsSource()).id)
        self.assertEqual((entry.events_status, store.event_counts["failure"]), ("ready", 1))
        parsed = cache.open(store.path, LogMetricsSource())
        cache.open_events(parsed, LogMetricsSource())
        self.assertEqual(self.registry.add_store(parsed).events_status, "ready")

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

    def test_open_run_of_a_directory(self):
        run_dir = self.dir / "run"
        run_dir.mkdir()
        write_log(run_dir / "du.log")
        write_log(run_dir / "cu.log")
        (run_dir / "data.bin").write_bytes(b"\0\1")
        run = self.registry.open_run(run_dir)
        self.assertEqual((run.is_dir, run.directory), (True, run_dir))
        self.assertEqual([self.registry.entries()[i].path.name for i in run.source_ids], ["cu.log", "du.log"])
        self.assertIs(self.registry.open_run(run_dir), run)
        file_run = self.registry.open_run(run_dir / "du.log")
        self.assertEqual((file_run.is_dir, file_run.directory, file_run.source_ids), (False, run_dir, [run.source_ids[1]]))
        (self.dir / "empty").mkdir()
        with self.assertRaisesRegex(OpenError, "no supported files"):
            self.registry.open_run(self.dir / "empty")

    def test_files_parsed_on_request(self):
        run_dir = self.dir / "run"
        run_dir.mkdir()
        write_log(run_dir / "gnb.log")
        mac = write_log(run_dir / "mac.log")
        cache = StoreCache(self.dir / "cache")
        registry = SourceRegistry(cache, [OnRequestLogs()], [self.dir])
        run = registry.open_run(run_dir)
        gnb_id, mac_id = run.source_ids
        self.assertEqual(wait_ready(registry, mac_id).status, "deferred")
        self.assertEqual(wait_ready(registry, gnb_id).status, "ready")
        # Opening it on its own is a request too.
        self.assertIs(registry.open(mac), registry.entries()[mac_id])
        self.assertEqual(wait_ready(registry, mac_id).status, "ready")
        # Once cached, a run opens it at once.
        again = SourceRegistry(cache, [OnRequestLogs()], [self.dir])
        run = again.open_run(run_dir)
        self.assertEqual([wait_ready(again, i).status for i in run.source_ids], ["ready", "ready"])

    def test_parse_a_deferred_file(self):
        run_dir = self.dir / "run"
        run_dir.mkdir()
        write_log(run_dir / "mac.log")
        registry = SourceRegistry(StoreCache(self.dir / "cache"), [OnRequestLogs()], [self.dir])
        (mac_id,) = registry.open_run(run_dir).source_ids
        self.assertEqual(registry.entries()[mac_id].status, "deferred")
        registry.parse(mac_id)
        self.assertEqual(wait_ready(registry, mac_id).status, "ready")
        with self.assertRaises(KeyError):
            registry.parse(99)

    def test_promote_a_file_to_its_run(self):
        du = write_log(self.dir / "du.log")
        write_log(self.dir / "other.log", branch="dev")
        run = self.registry.open_run(self.log)
        self.assertEqual((run.is_dir, run.path), (False, self.log))
        self.assertEqual(self.registry.related_files(run.id), [du])
        self.registry.promote_run(run.id)
        self.assertEqual((run.is_dir, run.path), (True, self.dir))
        self.assertEqual([self.registry.entries()[i].path.name for i in run.source_ids], ["gnb.log", "du.log"])
        self.assertEqual(self.registry.related_files(run.id), [])
        for source_id in run.source_ids:
            wait_ready(self.registry, source_id)

    def test_close_run_keeps_shared_sources(self):
        run = self.registry.open_run(self.dir)
        file_run = self.registry.open_run(self.log)
        self.assertEqual(file_run.source_ids, run.source_ids)
        # Closing a source does not stop its parsing, which must finish before the cache is removed.
        wait_ready(self.registry, run.source_ids[0])
        self.registry.close_run(run.id)
        self.assertEqual(self.registry.entries()[0].status in ("parsing", "ready"), True)
        self.registry.close_run(file_run.id)
        self.assertEqual(self.registry.entries()[0].status, "closed")
        with self.assertRaises(KeyError):
            self.registry.close_run(file_run.id)

    def test_add_and_remove_files_of_a_run(self):
        other = write_log(self.dir / "other.log")
        run = self.registry.open_run(self.log)
        self.registry.add_to_run(run.id, other)
        self.assertEqual(len(run.source_ids), 2)
        for source_id in run.source_ids:
            wait_ready(self.registry, source_id)
        (self.dir / "sub").mkdir()
        elsewhere = write_log(self.dir / "sub" / "cu.log")
        with self.assertRaisesRegex(OpenError, "not in the directory"):
            self.registry.add_to_run(run.id, elsewhere)
        self.registry.remove_from_run(run.id, run.source_ids[0])
        self.assertEqual(self.registry.entries()[0].status, "closed")
        self.registry.remove_from_run(run.id, run.source_ids[0])
        self.assertEqual(run.status, "closed")

    def test_unknown_and_unparsed_sources(self):
        with self.assertRaises(KeyError):
            self.registry.get_ready(3)


if __name__ == "__main__":
    unittest.main()
