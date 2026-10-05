# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import tempfile
import unittest
from pathlib import Path

from viz.sources.log_metrics import LogMetricsSource
from viz.store import QueryError, StoreCache

from .helpers import write_log


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = write_log(self.dir / "gnb.log")
        self.cache = StoreCache(self.dir / "cache")
        self.store = self.cache.open(self.log, LogMetricsSource())

    def tearDown(self):
        self.tmp.cleanup()

    def test_datasets_metadata(self):
        self.assertEqual(sorted(self.store.datasets), ["mac", "sched_ue"])
        ue = self.store.datasets["sched_ue"]
        self.assertEqual(ue["fields"]["dl_brate"], "number")
        self.assertEqual(ue["fields"]["rnti"], "text")
        self.assertEqual(ue["units"]["dl_brate"], "bps")
        self.assertEqual(ue["units"]["dl_bs"], "bytes")
        self.assertEqual(ue["context"], ["ue", "pci", "rnti"])
        self.assertEqual(self.store.meta["t_max"] - self.store.meta["t_min"], 9)

    def test_full_resolution_series(self):
        res = self.store.series("sched_ue", "dl_brate", group_by="ue")
        self.assertFalse(res["downsampled"])
        self.assertEqual(res["unit"], "bps")
        self.assertEqual([s["label"] for s in res["series"]], ["ue=0", "ue=1"])
        s = res["series"][0]
        self.assertEqual(s["v"], [1000 * i for i in range(10)])
        self.assertEqual(len(s["t"]), 10)
        # Line 1 is the boot line, then 4 lines per second for 2 UEs.
        self.assertEqual(s["record"][:2], [4, 8])

    def test_time_window_and_groups(self):
        t_min = self.store.meta["t_min"]
        res = self.store.series("sched_ue", "pusch_snr_db", t0=t_min + 2, t1=t_min + 4, group_by="ue", groups=["1"])
        self.assertEqual([s["label"] for s in res["series"]], ["ue=1"])
        self.assertEqual(res["series"][0]["v"], [21.5, 21.5, 21.5])

    def test_group_cap_without_explicit_groups(self):
        log = write_log(self.dir / "many.log", nof_seconds=2, nof_ues=30)
        store = self.cache.open(log, LogMetricsSource())
        res = store.series("sched_ue", "dl_brate", group_by="ue", max_groups=5)
        self.assertEqual(res["total_groups"], 30)
        self.assertEqual([s["group"] for s in res["series"]], [0, 1, 2, 3, 4])
        res = store.series("sched_ue", "dl_brate", group_by="ue", groups=["7", "29"], max_groups=5)
        self.assertEqual([s["group"] for s in res["series"]], [7, 29])

    def test_downsampled_series_keeps_extremes(self):
        res = self.store.series("mac", "wall_clock_latency_max", width=2, max_points=5)
        self.assertTrue(res["downsampled"])
        v = res["series"][0]["v"]
        self.assertIn(0, v)
        self.assertIn(90, v)
        self.assertLessEqual(len(v), 4)

    def test_invalid_queries(self):
        with self.assertRaises(QueryError):
            self.store.series("foo", "x")
        with self.assertRaises(QueryError):
            self.store.series("sched_ue", "rnti")
        with self.assertRaises(QueryError):
            self.store.series("sched_ue", 'dl_brate" OR 1=1 --')
        with self.assertRaises(QueryError):
            self.store.series("sched_ue", "dl_brate", group_by="nope")

    def test_context_values(self):
        self.assertEqual(self.store.context_values("sched_ue", "rnti"), ["0x4600", "0x4601"])

    def test_records_around(self):
        recs = self.store.records(around=4, count=3)
        self.assertEqual([r["record"] for r in recs], [3, 4, 5])
        self.assertIn("Scheduler UE ue=0", recs[1]["text"])

    def test_records_beyond_offset_interval(self):
        log = write_log(self.dir / "big.log", nof_seconds=60, nof_ues=20)
        store = self.cache.open(log, LogMetricsSource())
        recs = store.records(around=1200, count=1)
        self.assertEqual(recs[0]["record"], 1200)
        self.assertEqual(recs[0]["text"], log.read_text().splitlines()[1199])


class StoreCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = write_log(self.dir / "gnb.log")

    def tearDown(self):
        self.tmp.cleanup()

    def test_reuses_cache(self):
        cache = StoreCache(self.dir / "cache")
        cache.open(self.log, LogMetricsSource())
        calls = []
        cache.open(self.log, LogMetricsSource(), progress=lambda done, total: calls.append(done))
        self.assertEqual(calls, [])
        self.assertEqual(len(list((self.dir / "cache").glob("*.sqlite"))), 1)

    def test_rebuilds_when_source_changes(self):
        cache = StoreCache(self.dir / "cache")
        cache.open(self.log, LogMetricsSource())
        write_log(self.log, nof_seconds=12)
        store = cache.open(self.log, LogMetricsSource())
        self.assertEqual(store.meta["t_max"] - store.meta["t_min"], 11)

    def test_cache_dir_is_private(self):
        cache = StoreCache(self.dir / "cache")
        cache.open(self.log, LogMetricsSource())
        self.assertEqual((self.dir / "cache").stat().st_mode & 0o777, 0o700)

    def test_evicts_least_recently_used(self):
        cache = StoreCache(self.dir / "cache", max_bytes=1)
        other = write_log(self.dir / "other.log")
        cache.open(self.log, LogMetricsSource())
        cache.open(other, LogMetricsSource())
        self.assertEqual(len(list((self.dir / "cache").glob("*.sqlite"))), 1)

    def test_clear(self):
        cache = StoreCache(self.dir / "cache")
        cache.open(self.log, LogMetricsSource())
        cache.clear()
        self.assertEqual(list((self.dir / "cache").glob("*.sqlite")), [])

    def test_in_memory(self):
        cache = StoreCache(self.dir / "cache", enabled=False)
        store = cache.open(self.log, LogMetricsSource())
        self.assertEqual(len(store.series("mac", "nof_slots")["series"][0]["v"]), 10)
        self.assertFalse((self.dir / "cache").exists())


if __name__ == "__main__":
    unittest.main()
