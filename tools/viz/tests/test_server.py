# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import importlib.util
import tempfile
import unittest
from pathlib import Path

from .helpers import write_log


class DisplayNamesTest(unittest.TestCase):
    def test_unique_names_are_kept(self):
        from viz.server import display_names

        self.assertEqual(display_names([Path("/a/gnb.log"), Path("/b/ue.log")]), ["gnb.log", "ue.log"])

    def test_shared_names_get_first_differing_dir(self):
        from viz.server import display_names

        paths = [Path("/r/du-1/2026-07-30_20-53-05/du.log"), Path("/r/du-2/2026-07-30_20-53-09/du.log"), Path("/r/cu/cu.log")]
        self.assertEqual(display_names(paths), ["du-1/\u2026/du.log", "du-2/\u2026/du.log", "cu.log"])
        self.assertEqual(display_names([Path("/r/a/x.log"), Path("/r/b/x.log")]), ["a/x.log", "b/x.log"])


@unittest.skipUnless(importlib.util.find_spec("httpx"), "httpx not installed")
class ServerTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from viz.server import create_app
        from viz.sources.log_metrics import LogMetricsSource
        from viz.store import StoreCache

        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        store = StoreCache(tmp / "cache").open(write_log(tmp / "gnb.log"), LogMetricsSource())
        # A stand-in for the built frontend, so that the tests do not need Node.
        static = tmp / "static"
        (static / "assets").mkdir(parents=True)
        (static / "index.html").write_text("<!doctype html><title>ocudu-viz</title>")
        (static / "assets" / "app.js").write_text("console.log('app');")
        self.client = TestClient(create_app([store], static))
        self.not_built_client = TestClient(create_app([store], tmp / "missing"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_sources(self):
        res = self.client.get("/api/sources").json()
        self.assertEqual(res[0]["name"], "gnb.log")
        ue = next(d for d in res[0]["datasets"] if d["name"] == "sched_ue")
        brate = next(f for f in ue["fields"] if f["name"] == "dl_brate")
        self.assertEqual(brate, {"name": "dl_brate", "type": "number", "unit": "bps"})

    def test_series(self):
        res = self.client.get("/api/series", params={"source": 0, "dataset": "sched_ue", "field": "dl_brate", "group_by": "ue", "groups": ["0", "1"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["series"]), 2)

    def test_series_errors(self):
        self.assertEqual(self.client.get("/api/series", params={"source": 5, "dataset": "mac", "field": "x"}).status_code, 404)
        self.assertEqual(self.client.get("/api/series", params={"source": 0, "dataset": "mac", "field": "x"}).status_code, 400)

    def test_series_filter(self):
        res = self.client.get("/api/series", params={"source": 0, "dataset": "sched_ue", "field": "dl_brate", "group_by": "ue", "filter": "ue == 1"})
        self.assertEqual([s["label"] for s in res.json()["series"]], ["ue=1"])
        res = self.client.get("/api/series", params={"source": 0, "dataset": "sched_ue", "field": "dl_brate", "filter": "ue >"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Filter:", res.json()["detail"])

    def test_stats(self):
        res = self.client.get("/api/stats", params={"source": 0, "dataset": "mac", "field": "wall_clock_latency_max"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["series"][0]["max"], 90)

    def test_context(self):
        res = self.client.get("/api/context", params={"source": 0, "dataset": "sched_ue", "field": "ue"})
        self.assertEqual(res.json(), [0, 1])

    def test_records(self):
        res = self.client.get("/api/records", params={"source": 0, "around": 2, "count": 1})
        self.assertEqual(res.json()[0]["record"], 2)

    def test_static_index(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers["content-type"])

    def test_frontend_not_built(self):
        res = self.not_built_client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("not built", res.text)
        self.assertEqual(self.not_built_client.get("/api/sources").status_code, 200)


if __name__ == "__main__":
    unittest.main()
