# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import importlib.util
import tempfile
import unittest
from pathlib import Path

from parsers.log.adhoc import Spec

from viz.registry import OpenError, SourceRegistry
from viz.sources.log_metrics import LogMetricsSource
from viz.store import StoreCache

from .test_registry import wait_ready

# Slot decisions with values of tbs= on lines 2, 3 and 5, between other lines.
LOG = """\
2026-10-12T13:35:41.000000 [GNB     ] [I] Built in Release mode using commit abc on branch dev
2026-10-12T13:35:41.000100 [SCHED   ] [I] Slot decisions: DL: ue=0 c-rnti=0x44 tbs=5889 DL: ue=1 c-rnti=0x45 tbs=12
2026-10-12T13:35:41.000600 [SCHED   ] [I] Slot decisions: DL: ue=1 c-rnti=0x45 tbs=300
2026-10-12T13:35:41.001000 [RRC     ] [I] ue=0 something else
2026-10-12T13:35:41.001100 [SCHED   ] [I] Slot decisions: DL: ue=0 c-rnti=0x44 tbs=600
2026-10-12T13:35:41.002000 [RRC     ] [I] ue=1 the last line
"""


class AdhocTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = self.dir / "gnb.log"
        self.log.write_text(LOG)
        self.registry = SourceRegistry(StoreCache(self.dir / "cache"), [LogMetricsSource()], [self.dir])
        self.run = self.registry.open_run(self.log)
        wait_ready(self.registry, 0)

    def tearDown(self):
        self.tmp.cleanup()

    def open(self, spec):
        return wait_ready(self.registry, self.registry.open_adhoc(0, spec).id)

    def test_values_and_sparse_records(self):
        entry = self.open(Spec("tbs", split_key="ue"))
        self.assertEqual((entry.status, entry.parent), ("ready", 0))
        store = entry.store
        ds = store.datasets["adhoc"]
        self.assertEqual((ds["label"], ds["context"], ds["fields"]), ("tbs= by ue", ["ue"], {"tbs": "number", "ue": "text"}))
        series = store.series("adhoc", "tbs", split_by="ue")
        self.assertEqual({s["split"]: (s["v"], s["record"]) for s in series["series"]},
                         {"0": ([5889, 600], [2, 5]), "1": ([12, 300], [2, 3])})
        # Records are the lines with values only, each once.
        self.assertEqual([r["record"] for r in store.records(3, 10)], [2, 3, 5])
        self.assertEqual([r["record"] for r in store.records(after=2, count=1)], [3])
        self.assertEqual([r["record"] for r in store.records(before=5, count=5)], [2, 3])
        self.assertEqual(store.records(after=5, count=5), [])
        self.assertTrue(store.records(3, 1)[0]["text"].endswith("tbs=300"))
        text = store.records(3, 1)[0]["text"]
        start, end = entry.source_type.field_spans(text)["tbs"]
        self.assertEqual(text[start:end], "tbs=300")

    def test_filter_and_reuse(self):
        entry = self.open(Spec("tbs", filter="tbs=300|tbs=600"))
        self.assertEqual(entry.store.series("adhoc", "tbs")["series"][0]["v"], [300, 600])
        # The same spec is the same source, also when asked from an ad-hoc metric of the log.
        self.assertEqual(self.registry.open_adhoc(entry.id, Spec("tbs", filter="tbs=300|tbs=600")).id, entry.id)

    def test_marked_lines(self):
        entry = self.open(Spec(None, filter="rrc"))
        store = entry.store
        # No dataset: the lines are records and events.
        self.assertEqual((store.datasets, [r["record"] for r in store.records(1, 10)]), ({}, [4, 6]))
        self.assertEqual(store.event_counts, {"adhoc": 2})
        events = store.events(None, None, None, None, 10, None)["events"]
        self.assertEqual([(e["record"], e["type"], e["layer"], e["ue"]) for e in events], [(4, "/rrc/", "RRC", 0), (6, "/rrc/", "RRC", 1)])
        self.assertTrue(events[0]["text"].endswith("something else"))

    def test_log_records_after_and_before(self):
        store = self.registry.entries()[0].store
        self.assertEqual([r["record"] for r in store.records(after=4, count=5)], [5, 6])
        self.assertEqual([r["record"] for r in store.records(before=3, count=5)], [1, 2])
        self.assertEqual(store.records(before=1, count=5), [])

    def test_closing_the_log_closes_its_metrics(self):
        entry = self.open(Spec("tbs"))
        self.registry.close(0)
        self.assertEqual(self.registry.entries()[entry.id].status, "closed")
        with self.assertRaises(OpenError):
            self.registry.open_adhoc(0, Spec("tbs"))

    def test_opening_a_file_does_not_return_a_metric(self):
        self.open(Spec("tbs"))
        self.assertEqual(self.registry.open(self.log).id, 0)


@unittest.skipUnless(importlib.util.find_spec("httpx"), "httpx not installed")
class AdhocApiTest(AdhocTest):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient

        from viz.server import create_app

        self.client = TestClient(create_app(self.registry, self.dir / "missing"))

    def test_api(self):
        res = self.client.post("/api/sources/0/adhoc", json={"key": "tbs", "split_key": "ue"})
        self.assertEqual(res.status_code, 200, res.text)
        source_id = res.json()["id"]
        wait_ready(self.registry, source_id)
        info = self.client.get("/api/sources").json()[source_id]
        self.assertEqual((info["name"], info["parent"], info["adhoc"]),
                         ("gnb.log › tbs= by ue", 0, {"key": "tbs", "filter": None, "split_key": "ue"}))
        records = self.client.get("/api/records", params={"source": source_id, "after": 2, "count": 5}).json()
        self.assertEqual([r["record"] for r in records], [3, 5])
        self.assertEqual(self.client.post("/api/sources/0/adhoc", json={"key": "tbs", "filter": "(("}).status_code, 400)
        self.assertEqual(self.client.post("/api/sources/9/adhoc", json={"key": "tbs"}).status_code, 404)
        self.assertEqual(self.client.get("/api/records", params={"source": 0, "after": 1, "before": 3}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
