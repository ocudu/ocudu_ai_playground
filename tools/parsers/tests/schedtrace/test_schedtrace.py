# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import json
import unittest
from pathlib import Path

from parsers import schedtrace

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

    def test_fields_of_newer_schemas_are_ignored(self):
        (stop,) = schedtrace.read(DATA / "cell_stop_newer.bin")
        self.assertEqual(stop, {"timestamp_us": 1, "type": "CellStopEvent", "cell_idx": 3})

    def test_schema(self):
        tables = schedtrace.decoder().schema.tables
        # A union field takes two slots, its type first.
        self.assertEqual([(f.name, f.slot) for f in tables["CellSlotEvent"].fields],
                         [("slot_tx", 0), ("latency_us", 1), ("inputs", 3), ("decision", 4)])
        self.assertIsNone(next(f for f in tables["VrbAlloc"].fields if f.name == "vrb_second_hop_start").default)
