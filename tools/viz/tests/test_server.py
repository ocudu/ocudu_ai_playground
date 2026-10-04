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
        store = StoreCache(tmp / "cache").open(write_log(tmp / "gnb.log", executors=True), LogMetricsSource())
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

    def test_sources_dataset_label_and_instance(self):
        res = self.client.get("/api/sources").json()
        ds = next(d for d in res[0]["datasets"] if d["name"] == "exec")
        self.assertEqual((ds["label"], ds["instance"]), ("executors", "executor"))
        self.assertEqual(ds["t_max"] - ds["t_min"], 9)

    def test_series_instance(self):
        res = self.client.get("/api/series", params={"source": 0, "dataset": "exec", "field": "task_avg", "instance": "du_ctrl_exec"})
        self.assertEqual(res.json()["series"][0]["v"], [20] * 10)

    def test_series(self):
        res = self.client.get("/api/series", params={"source": 0, "dataset": "sched_ue", "field": "dl_brate", "split_by": "ue", "split_values": ["0", "1"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["series"]), 2)

    def test_series_errors(self):
        self.assertEqual(self.client.get("/api/series", params={"source": 5, "dataset": "mac", "field": "x"}).status_code, 404)
        self.assertEqual(self.client.get("/api/series", params={"source": 0, "dataset": "mac", "field": "x"}).status_code, 400)

    def test_series_filter(self):
        res = self.client.get("/api/series", params={"source": 0, "dataset": "sched_ue", "field": "dl_brate", "split_by": "ue", "filter": "ue == 1"})
        self.assertEqual([s["label"] for s in res.json()["series"]], ["ue=1"])
        res = self.client.get("/api/series", params={"source": 0, "dataset": "sched_ue", "field": "dl_brate", "filter": "ue >"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Filter:", res.json()["detail"])

    def test_stats(self):
        res = self.client.get("/api/stats", params={"source": 0, "dataset": "mac", "field": "wall_clock_latency_max"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["series"][0]["max"], 90)

    def test_histogram(self):
        res = self.client.get("/api/histogram", params={"source": 0, "dataset": "sched_ue", "field": "dl_brate", "bins": 2})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["series"][0]["counts"], [10, 10])

    def test_table(self):
        res = self.client.get("/api/table", params={"source": 0, "dataset": "sched_ue", "limit": 3}).json()
        self.assertEqual((res["total"], len(res["rows"])), (20, 3))
        names = [f["name"] for f in res["fields"]]
        self.assertEqual(names[:3], ["ue", "pci", "rnti"])
        brate = res["fields"][names.index("dl_brate")]
        self.assertEqual((brate["unit"], brate["context"]), ("bps", False))
        self.assertEqual(len(res["rows"][0]), 2 + len(names))

    def test_table_csv(self):
        params = {"source": 0, "dataset": "exec", "instance": "cell_exec", "fields": ["executor", "task_avg"]}
        res = self.client.get("/api/table.csv", params=params)
        self.assertEqual(res.status_code, 200)
        self.assertIn('filename="gnb_exec_cell_exec.csv"', res.headers["content-disposition"])
        lines = res.text.splitlines()
        self.assertEqual(lines[0], "time_utc,line,executor,task_avg_us")
        self.assertEqual(len(lines), 11)
        self.assertTrue(lines[1].startswith("2026-06-29T14:10:00.000000Z,"))
        self.assertTrue(lines[1].endswith(",cell_exec,10"))

    def test_table_csv_percent_unit(self):
        res = self.client.get("/api/table.csv", params={"source": 0, "dataset": "exec", "fields": ["cpu_load"]})
        self.assertEqual(res.text.splitlines()[0], "time_utc,line,cpu_load_pct")

    def test_table_csv_errors(self):
        base = {"source": 0, "dataset": "mac"}
        self.assertEqual(self.client.get("/api/table.csv", params={**base, "filter": "nope > 1"}).status_code, 400)
        self.assertEqual(self.client.get("/api/table.csv", params={**base, "fields": ["nope"]}).status_code, 400)

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

    def test_static_files_are_revalidated(self):
        res = self.client.get("/assets/app.js")
        self.assertEqual(res.headers["cache-control"], "no-cache")
        etag = res.headers["etag"]
        self.assertEqual(self.client.get("/assets/app.js", headers={"if-none-match": etag}).status_code, 304)

    def test_sources_status(self):
        src = self.client.get("/api/sources").json()[0]
        self.assertEqual((src["status"], src["progress"], src["error"]), ("ready", 1.0, None))

    def test_open_from_page(self):
        from fastapi.testclient import TestClient

        from viz.registry import SourceRegistry
        from viz.server import create_app
        from viz.sources.log_metrics import LogMetricsSource
        from viz.store import StoreCache

        from .test_registry import wait_ready

        tmp = Path(self.tmp.name).resolve()
        (tmp / "logs").mkdir()
        log = write_log(tmp / "logs" / "du.log")
        registry = SourceRegistry(StoreCache(tmp / "cache2"), [LogMetricsSource()], [tmp])
        client = TestClient(create_app(registry, tmp / "missing"))
        self.assertEqual(client.get("/api/roots").json(), {"roots": [str(tmp)], "can_open": True})
        listing = client.get("/api/fs", params={"path": str(tmp / "logs")}).json()
        self.assertEqual([e["name"] for e in listing["entries"]], ["du.log"])
        self.assertEqual(client.get("/api/fs", params={"path": "/etc"}).status_code, 400)
        res = client.post("/api/sources", json={"path": str(log)})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["id"], 0)
        wait_ready(registry, 0)
        self.assertEqual(client.get("/api/sources").json()[0]["status"], "ready")
        self.assertEqual(client.get("/api/series", params={"source": 0, "dataset": "mac", "field": "nof_slots"}).status_code, 200)
        self.assertEqual(client.post("/api/sources", json={"path": "/etc/hostname"}).status_code, 400)
        self.assertEqual(client.delete("/api/sources/0").json()["status"], "closed")
        self.assertEqual(client.get("/api/series", params={"source": 0, "dataset": "mac", "field": "nof_slots"}).status_code, 409)
        self.assertEqual(client.delete("/api/sources/9").status_code, 404)

    def test_open_without_registry(self):
        res = self.client.post("/api/sources", json={"path": "/tmp"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.client.get("/api/roots").json()["can_open"], False)

    def test_frontend_not_built(self):
        res = self.not_built_client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("not built", res.text)
        self.assertEqual(self.not_built_client.get("/api/sources").status_code, 200)


if __name__ == "__main__":
    unittest.main()
