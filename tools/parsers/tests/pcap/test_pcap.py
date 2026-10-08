# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import shutil
import tempfile
import unittest
from pathlib import Path

from parsers.pcap import e1ap, f1ap, ngap, overview, run, timeline, values
from parsers.pcap.tshark import Tshark, _filter_stderr, split_fields

# A single-UE F1AP capture: F1Setup, RRC and NAS attach, and UEContextRelease.
F1AP_PCAP = Path(__file__).resolve().parent / "f1ap_pcap_test.pcap"


class FakeTshark:
    """Tshark returning fixed rows for any extraction."""

    def __init__(self, rows):
        self.rows = rows

    def iter_fields(self, pcap, fields, **kwargs):
        return iter(self.rows)


class ValuesTest(unittest.TestCase):
    def test_epoch_to_iso(self):
        self.assertEqual(values.epoch_to_iso("1759326404.3901"), "2025-10-01T13:46:44.390")
        self.assertEqual(values.epoch_to_iso("x"), "x")

    def test_to_int(self):
        self.assertEqual(values.to_int("0x41"), 0x41)
        self.assertEqual(values.to_int("65"), 65)
        self.assertIsNone(values.to_int(""))


class TsharkHelpersTest(unittest.TestCase):
    def test_split_fields(self):
        self.assertEqual(split_fields("a\tb", 3), ["a", "b", ""])
        self.assertEqual(split_fields("a\tb\tc", 2), ["a", "b"])

    def test_filter_stderr(self):
        stderr = (
            "tshark: Error loading table 'User DLTs Table': Permission denied\n"
            "tshark: Could not open your disabled protocols file\n"
            '"/home/u/.config/wireshark/disabled_protos": Permission denied.\n'
            "tshark: Some fields aren't valid:\n"
        )
        self.assertEqual(_filter_stderr(stderr), "tshark: Some fields aren't valid:")

    def test_cache_path_depends_on_tag(self):
        ts = Tshark("/tmp/work")
        self.assertNotEqual(ts.cache_path("a.pcap", "x"), ts.cache_path("a.pcap", "y"))
        self.assertEqual(ts.cache_path("a.pcap", "x").parent, Path("/tmp/work"))


class F1apDecodeTest(unittest.TestCase):
    def row(self, code, srbid=None, container="", elements=None):
        return {"code": code, "srbid": srbid, "rrc_container": container, "rrc_elements": elements or {}}

    def test_resolve_rrc(self):
        self.assertEqual(f1ap.resolve_rrc(self.row("12", elements={"rrcSetup": "", "rrcRelease": "1"})), "rrcRelease")
        self.assertIsNone(f1ap.resolve_rrc(self.row("12")))
        self.assertEqual(f1ap.resolve_rrc(self.row("11", container="00")), "rrcSetupRequest")
        self.assertEqual(f1ap.resolve_rrc(self.row("6", srbid="0", container="00")), "rrcReject")
        self.assertEqual(f1ap.resolve_rrc(self.row("6", srbid="1", container="0102")), "rrcRelease?")
        self.assertIsNone(f1ap.resolve_rrc(self.row("1", container="00")))


class UeIdsTest(unittest.TestCase):
    def test_ngap_ue_ids_attach_the_amf_id(self):
        rows = [
            ["1", "10.0", "21", "", ""],
            ["2", "11.0", "15", "1", ""],
            ["3", "12.0", "14", "1", "7"],
            ["4", "13.0", "15", "2", ""],
        ]
        ues = ngap.ue_ids(FakeTshark(rows), "ngap.pcap")
        self.assertEqual([(u["frame"], u["message"], u["ran_ue_ngap_id"], u["amf_ue_ngap_id"]) for u in ues],
                         [(2, "InitialUEMessage", "1", "7"), (4, "InitialUEMessage", "2", None)])

    def test_e1ap_ue_ids_names(self):
        ues = e1ap.ue_ids(FakeTshark([["5", "1.5", "8", "3", "9"]]), "e1ap.pcap")
        self.assertEqual(ues[0]["e1_cp_ue_id"], "3")
        self.assertEqual(ues[0]["e1_up_ue_id"], "9")
        self.assertEqual(ues[0]["message"], "bearerContextSetup")


class RunDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolve(self):
        (self.dir / "f1ap.pcap").write_bytes(b"x")
        self.assertIn("bail", run.resolve(self.dir))
        self.assertFalse(run.is_run_dir(self.dir))
        (self.dir / "ngap.pcap").write_bytes(b"x")
        self.assertTrue(run.is_run_dir(self.dir))
        res = run.resolve(self.dir)
        self.assertEqual((res["kind"], res["present"]), ("run directory", ["f1ap", "ngap"]))
        res = run.resolve(self.dir / "ngap.pcap")
        self.assertEqual((res["kind"], res["siblings"]), ("single pcap", ["f1ap"]))
        self.assertIn("bail", run.resolve(self.dir / "missing.pcap"))

    def test_check_empty_pcap(self):
        (self.dir / "mac.pcap").write_bytes(b"")
        res = run.check_pcap(Tshark(self.dir / "work"), self.dir / "mac.pcap")
        self.assertEqual((res["ok"], res["reason"]), (False, "empty (0 bytes)"))


@unittest.skipUnless(shutil.which("tshark"), "tshark not installed")
class F1apPcapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_events = []
        self.tshark = Tshark(self.tmp.name, on_cache=lambda path, hit: self.cache_events.append(hit))

    def tearDown(self):
        self.tmp.cleanup()

    def test_messages(self):
        records = f1ap.messages(self.tshark, F1AP_PCAP)
        self.assertEqual(len(records), 32)
        self.assertEqual(records[0]["message"], "F1Setup")
        setup_req = next(r for r in records if r["rrc"] == "rrcSetupRequest")
        self.assertEqual((setup_req["message"], setup_req["crnti"]), ("InitialULRRCMessageTransfer", "17921"))
        self.assertTrue(any(r["nas"] == "RegistrationRequest" for r in records))

    def test_ue_ids_are_cached(self):
        first = f1ap.ue_ids(self.tshark, F1AP_PCAP)
        self.assertEqual(f1ap.ue_ids(self.tshark, F1AP_PCAP), first)
        self.assertEqual(self.cache_events, [False, True])
        self.assertEqual(len(first), 1)
        self.assertEqual((first[0]["cu_ue_f1ap_id"], first[0]["crntis"]), ("0", ["17921"]))

    def test_check_pcap(self):
        res = run.check_pcap(self.tshark, F1AP_PCAP)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["dissector"], "f1ap")

    def test_overview(self):
        # The protocol of a pcap is its file stem.
        pcap = Path(self.tmp.name) / "f1ap.pcap"
        shutil.copy(F1AP_PCAP, pcap)
        summary = overview.summarise(self.tshark, pcap, top=3)
        self.assertEqual((summary["proto"], summary["packets"], summary["failures"]), ("f1ap", 32, 0))
        self.assertEqual(len(summary["top_procedures"]), 3)
        self.assertEqual(summary["distinct_ues_by_label"]["cu"], ["0"])
        counts = overview.proc_code_counts(self.tshark, F1AP_PCAP, "f1ap", initiating_only=True)
        self.assertEqual(counts["1"], 1)

    def test_events(self):
        events = timeline.events(self.tshark, F1AP_PCAP, "f1ap")
        self.assertEqual(len(events), 32)
        self.assertEqual(events[0]["summary"], "procCode=1")
        self.assertTrue(any(e["ue_ids"] for e in events))


if __name__ == "__main__":
    unittest.main()
