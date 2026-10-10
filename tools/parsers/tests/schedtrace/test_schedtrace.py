# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from parsers import schedtrace
from parsers.schedtrace import _generated, codegen, grid

# Trace built by data/make_fixtures.sh with flatc from the JSON events, and flatc's decoding of it.
DATA = Path(__file__).parent / "data"
EVENTS = ("cell_start", "cell_slot", "cell_stop")


def from_flatc(value):
    """flatc's JSON as the decoder gives it: unions with their type in."""
    if isinstance(value, list):
        return [from_flatc(v) for v in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for key, v in value.items():
        if key.endswith("_type") and key[: -len("_type")] in value:
            continue
        kind = value.get(f"{key}_type")
        if isinstance(v, dict) and kind is not None:
            v = {"type": kind, **v}
        elif isinstance(v, list) and kind is not None:
            v = [{"type": k, **e} for k, e in zip(kind, v)]
        out[key] = from_flatc(v)
    return out


def present(value):
    """A value without its absent fields, which flatc leaves out or gives as null."""
    if isinstance(value, dict):
        return {k: present(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [present(v) for v in value]
    return value


class SchedtraceTest(unittest.TestCase):
    def test_events_match_flatc(self):
        events = list(schedtrace.read(DATA / "schedtrace_cell0.bin"))
        self.assertEqual([e["type"] for e in events], ["CellStartEvent", "CellSlotEvent", "CellStopEvent"])
        for name, event in zip(EVENTS, events):
            ref = from_flatc(json.loads((DATA / f"{name}.flatc.json").read_text()))
            value = ref.pop("value")
            ref = {**ref, **value}
            self.assertEqual(present(event), present(ref), name)

    def test_slot_event(self):
        slot = list(schedtrace.read(DATA / "schedtrace_cell0.bin"))[1]
        self.assertEqual((slot["slot_tx"], slot["latency_us"]), (12345, 42))
        # A vector of unions, with structs inline and enums by name.
        rach, harq, sr, csi = slot["inputs"]
        self.assertEqual(rach["occasions"][0]["preambles"], [{"preamble_id": 23, "tc_rnti": 17922, "time_advance": -5}])
        self.assertEqual((harq["type"], harq["status"]), ("HarqAckEvent", "Dtx"))
        self.assertEqual(sr, {"type": "SrEvent", "slot_rx": 12342, "ue_idx": 1, "rnti": 17922})
        # Optional scalars are None when absent.
        self.assertEqual((csi["ri"], csi["li"], csi["pmi"]["type"], csi["pmi"]["i_1_2"]), (2, None, "PmiTypeISinglePanel", None))
        decision = slot["decision"]
        self.assertEqual(decision["ue_pdschs"][0]["rbs"], {"type": "RbgAlloc", "nof_rbgs": 9, "bitmap": 511})
        self.assertEqual(decision["rar_pdschs"][0]["grants"][0]["tpc"], -1)
        self.assertIsNone(decision["ul_pdcchs"])

    def test_incomplete_last_event(self):
        data = (DATA / "schedtrace_cell0.bin").read_bytes()
        self.assertEqual(len(list(schedtrace.events(data[:-5]))), 2)
        self.assertEqual(list(schedtrace.events(b"")), [])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "schedtrace_cell0.bin"
            path.write_bytes(data[:-5])
            self.assertEqual(len(list(schedtrace.read(path))), 2)

    def test_read_matches_events(self):
        data = (DATA / "schedtrace_cell0.bin").read_bytes()
        self.assertEqual(list(schedtrace.read(DATA / "schedtrace_cell0.bin")), list(schedtrace.events(data)))

    def test_fields_of_newer_schemas_are_ignored(self):
        (stop,) = schedtrace.read(DATA / "cell_stop_newer.bin")
        self.assertEqual(stop, {"timestamp_us": 1, "type": "CellStopEvent", "cell_idx": 3})

    def test_schema(self):
        tables = schedtrace.decoder().schema.tables
        # A union field takes two slots, its type first.
        self.assertEqual([(f.name, f.slot) for f in tables["CellSlotEvent"].fields],
                         [("slot_tx", 0), ("latency_us", 1), ("inputs", 3), ("decision", 4)])
        self.assertIsNone(next(f for f in tables["VrbAlloc"].fields if f.name == "vrb_second_hop_start").default)


class GeneratedTest(unittest.TestCase):
    def tearDown(self):
        schedtrace._stale.cache_clear()

    def test_up_to_date(self):
        self.assertEqual(_generated.SCHEMA_HASH, codegen.source_hash(),
                         "_generated.py is stale, regenerate it with python -m parsers.schedtrace.codegen")

    def test_matches_decoder(self):
        dec = schedtrace.decoder()
        for name in ("schedtrace_cell0.bin", "cell_stop_newer.bin"):
            data = memoryview((DATA / name).read_bytes())
            for offset in schedtrace.offsets(data):
                size = int.from_bytes(data[offset : offset + 4], "little")
                buf = data[offset + 4 : offset + 4 + size]
                # Compared as lists of items, so that the order of the fields matters too.
                self.assertEqual(list(_generated.root(buf).items()), list(dec.root(buf).items()), name)

    def test_stale_falls_back_to_decoder(self):
        schedtrace._stale.cache_clear()
        with mock.patch.object(_generated, "SCHEMA_HASH", "stale"), self.assertWarns(UserWarning):
            self.assertEqual(schedtrace._root(False), schedtrace.decoder().root)
            self.assertEqual(schedtrace._root(True), schedtrace.decoder().root)

    def test_grid_only(self):
        full = list(schedtrace.read(DATA / "schedtrace_cell0.bin"))
        brief = list(schedtrace.read(DATA / "schedtrace_cell0.bin", grid_only=True))
        cell = grid.cell_of(full[0])
        self.assertEqual(brief[0], full[0])
        self.assertEqual(grid.allocations(brief[1], cell), grid.allocations(full[1], cell))
        self.assertEqual([i["type"] for i in brief[1]["inputs"]], [i["type"] for i in full[1]["inputs"]])
        self.assertEqual((brief[1]["slot_tx"], brief[1]["latency_us"]), (full[1]["slot_tx"], full[1]["latency_us"]))
        self.assertNotIn("dl_pdcchs", brief[1]["decision"])
        self.assertEqual(brief[2], full[2])

    def test_grid_fields_exist(self):
        tables = schedtrace.decoder().schema.tables
        for name, fields in codegen.GRID_FIELDS.items():
            self.assertLessEqual(set(fields), {f.name for f in tables[name].fields}, name)


class GridTest(unittest.TestCase):
    def setUp(self):
        start, self.slot, _ = schedtrace.read(DATA / "schedtrace_cell0.bin")
        self.cell = grid.cell_of(start)

    def test_allocations(self):
        rects = grid.allocations(self.slot, self.cell)
        by_channel = {}
        for r in rects:
            by_channel.setdefault(r["channel"], []).append((r["dir"], r["sym_start"], r["sym_length"], r["crb_start"], r["crb_length"]))
        # 9 RBGs of 4 PRBs in a 52-PRB BWP starting at CRB 2, the first RBG cut short at CRB 4, merged.
        self.assertEqual(by_channel["PDSCH"], [("DL", 1, 13, 2, 34)])
        self.assertEqual(by_channel["PUSCH"], [("UL", 0, 14, 5, 20)])
        # The RAR PDSCH of the trace has no symbols, so no rectangle.
        self.assertNotIn("RAR", by_channel)
        self.assertEqual(by_channel["SSB"], [("DL", 2, 4, 10, 20)])
        pdsch = next(r for r in rects if r["channel"] == "PDSCH")
        self.assertEqual((pdsch["rnti"], pdsch["mcs"], pdsch["tbs"], pdsch["item"]), (17921, 27, 12345, ["ue_pdschs", 0]))

    def test_pucch_hops(self):
        slot = {"decision": {"pucchs": [{"rnti": 1, "res_idx": 1, "nof_bits_harq_ack": 2, "nof_bits_sr": 0, "nof_bits_csi1": 0}]}}
        rects = grid.allocations(slot, self.cell)
        # Resource 1: format 2 of 2 PRBs at PRB 40, hopping to PRB 7 for the second of its 2 symbols.
        self.assertEqual([(r["sym_start"], r["sym_length"], r["crb_start"], r["crb_length"]) for r in rects], [(12, 1, 40, 2), (13, 1, 7, 2)])

    def test_occupancy(self):
        rects = [{"channel": "PDSCH", "crb_start": 2, "crb_length": 6, "sym_length": 7}]
        self.assertEqual(grid.occupancy(rects, 4), {(0, "PDSCH"): 0.25, (1, "PDSCH"): 0.5})

    def test_rbg_size(self):
        self.assertEqual([grid.rbg_size(n) for n in (24, 52, 106, 273)], [2, 4, 8, 16])
