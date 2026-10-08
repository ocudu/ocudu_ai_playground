# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

from viz.sources.base import RunIdentity
from viz.sources.log_metrics import LogMetricsSource
from viz.sources.pcap import PcapSource
from viz.store import StoreCache

from .helpers import write_log

# A single-UE F1AP capture of the parser tests: F1Setup, RRC and NAS attach, and UEContextRelease.
F1AP_PCAP = Path(__file__).resolve().parents[2] / "parsers" / "tests" / "pcap" / "f1ap_pcap_test.pcap"


class RunIdentityTest(unittest.TestCase):
    def test_same_run(self):
        log = RunIdentity(("Release", "abc", "main"), 100.0, 200.0)
        self.assertTrue(log.same_run(RunIdentity(None, 150.0, 400.0)))
        self.assertTrue(log.same_run(RunIdentity(None, 250.0, 300.0)))
        self.assertFalse(log.same_run(RunIdentity(None, 300.0, 400.0)))
        self.assertFalse(log.same_run(RunIdentity(("Release", "abc", "dev"), 100.0, 200.0)))

    def test_log_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            identity = LogMetricsSource().run_identity(write_log(Path(tmp) / "gnb.log", branch="dev"))
        self.assertEqual(identity.build, ("Release", "0123456789", "dev"))
        self.assertLess(identity.start, identity.end)


@unittest.skipUnless(shutil.which("tshark"), "tshark not installed")
class PcapSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        # The protocol comes from the frames, not the file name.
        self.pcap = self.dir / "capture.pcap"
        shutil.copy(F1AP_PCAP, self.pcap)
        self.source = PcapSource(self.dir / "work")
        cache = StoreCache(self.dir / "cache")
        self.store = cache.open(self.pcap, self.source)
        cache.open_events(self.store, self.source)

    def tearDown(self):
        self.tmp.cleanup()

    def test_accepts(self):
        self.assertTrue(self.source.accepts(self.pcap))
        self.assertFalse(self.source.accepts(write_log(self.dir / "gnb.log")))

    def test_on_request(self):
        on_request = [n for n in ("mac.pcap", "rlc.pcap", "du_mac.pcap", "MAC-1.pcap", "f1ap.pcap", "machine.pcap") if self.source.on_request(Path(n))]
        self.assertEqual(on_request, ["mac.pcap", "rlc.pcap", "du_mac.pcap", "MAC-1.pcap"])

    def test_messages_dataset(self):
        ds = self.store.datasets["messages"]
        self.assertEqual(ds["label"], "F1AP messages")
        self.assertEqual(ds["units"], {"len": "bytes"})
        self.assertIn("du_ue_f1ap_id", ds["context"])
        rows = list(self.store.table_rows("messages", None, None, None, None, ["procedure", "rrc", "c_rnti"], 5))
        self.assertEqual([r[1] for r in rows[:3]], [1, 2, 3])
        self.assertEqual(rows[2][2:], ("InitialULRRCMessageTransfer", "rrcSetupRequest", "0x4601"))

    def test_records_are_frame_summaries(self):
        records = self.store.records(3, 3)
        self.assertEqual([r["record"] for r in records], [2, 3, 4])
        self.assertIn("[F1AP/NR RRC] InitialULRRCMessageTransfer, RRC Setup Request", records[1]["text"])
        self.assertIn("F1 Application Protocol (InitialULRRCMessageTransfer)", self.source.record_detail(self.pcap, 3))

    def test_events_and_lanes(self):
        self.assertEqual(self.store.event_counts, {"f1ap": 12, "rrc": 20})
        trace = self.store.trace()
        self.assertEqual([(lane["label"], lane["rnti"]) for lane in trace["lanes"]], [("du_f1ap=0 cu_f1ap=0", "0x4601")])
        first_rrc = next(e for e in trace["events"] if e["category"] == "rrc")
        self.assertEqual((first_rrc["type"], first_rrc["layer"], first_rrc["rnti"]), ("rrcSetupRequest", "F1AP", "0x4601"))
        # F1Setup belongs to no UE.
        self.assertIsNone(trace["events"][0]["lane"])

    def test_run_identity(self):
        identity = self.source.run_identity(self.pcap)
        self.assertIsNone(identity.build)
        self.assertEqual(self.store.meta["t_min"], identity.start)


@unittest.skipUnless(shutil.which("tshark") and importlib.util.find_spec("httpx"), "tshark or httpx not installed")
class PcapServerTest(unittest.TestCase):
    def test_record_detail(self):
        from fastapi.testclient import TestClient

        from viz.registry import SourceRegistry
        from viz.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = PcapSource(tmp / "work")
            store = StoreCache(tmp / "cache").open(F1AP_PCAP, source)
            registry = SourceRegistry()
            registry.add_run(F1AP_PCAP, False, [registry.add_store(store, source).id])
            client = TestClient(create_app(registry, tmp / "missing"))
            info = client.get("/api/sources").json()[0]
            self.assertEqual((info["type"], info["has_detail"]), ("pcap", True))
            res = client.get("/api/records/detail", params={"source": 0, "record": 3}).json()
            self.assertIn("InitialULRRCMessageTransfer", res["text"])

    def test_run_trace(self):
        from fastapi.testclient import TestClient

        from viz.registry import SourceRegistry
        from viz.server import create_app

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cache = StoreCache(tmp / "cache")
            pcap_source, log_source = PcapSource(tmp / "work"), LogMetricsSource()
            pcap = cache.open(F1AP_PCAP, pcap_source)
            cache.open_events(pcap, pcap_source)
            log = cache.open(write_log(tmp / "gnb.log", events=True), log_source)
            cache.open_events(log, log_source)
            registry = SourceRegistry()
            ids = [registry.add_store(log, log_source).id, registry.add_store(pcap, pcap_source).id]
            registry.add_run(tmp, True, ids)
            registry.add_run(tmp / "gnb.log", False, [ids[0]])
            client = TestClient(create_app(registry, tmp / "missing"))
            trace = client.get("/api/runs/0/trace").json()
            # The log is from another time than the pcap, so its UE lanes join no F1AP UE context.
            self.assertIn("du_f1ap=0 cu_f1ap=0", [lane["label"] for lane in trace["lanes"]])
            self.assertEqual({e["source"] for e in trace["events"]}, set(ids))
            self.assertEqual(trace["total_lanes"], 1 + len(log.trace()["lanes"]))
            self.assertEqual(client.get("/api/runs/1/trace").status_code, 400)


if __name__ == "__main__":
    unittest.main()
