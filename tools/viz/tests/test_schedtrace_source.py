# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from viz.sources.schedtrace import SchedtraceSource, _slot_times
from viz.store import StoreCache

# Trace of a cell start, a slot and a cell stop, of the tests of parsers.schedtrace.
TRACE = Path(__file__).resolve().parents[2] / "parsers" / "tests" / "schedtrace" / "data" / "schedtrace_cell0.bin"


class SchedtraceSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / "schedtrace_cell0.bin"
        shutil.copy(TRACE, self.path)
        self.source = SchedtraceSource()
        self.store = StoreCache(self.dir / "cache").open(self.path, self.source)

    def tearDown(self):
        self.tmp.cleanup()

    def test_accepts(self):
        self.assertTrue(self.source.accepts(self.path))
        other = self.dir / "trace.bin"
        shutil.copy(TRACE, other)
        self.assertFalse(self.source.accepts(other))
        self.assertTrue(self.source.on_request(self.path))

    def test_grid_meta(self):
        meta = self.store.meta["grid"]
        # 15 kHz subcarriers: 1 ms slots.
        self.assertEqual((meta["nof_crbs"], meta["slot_duration_s"], meta["group_size"]), (54, 0.001, 4))
        # Its only slot has both PDSCH and PUSCH, which only FDD cells have.
        self.assertEqual(meta["duplex"], "FDD")
        self.assertEqual(self.store.meta["t_min"], 1700000000.0)
        # The end of the last slot, the stop event's time plus a slot.
        self.assertAlmostEqual(self.store.meta["t_max"], 1700000000.002, places=6)

    def test_grid_window(self):
        res = self.source.grid(self.path, self.store, None, None, 1000)
        self.assertEqual((res["mode"], res["nof_slots"]), ("rects", 1))
        self.assertEqual(sorted({r["channel"] for r in res["rects"]}), ["PDCCH", "PDSCH", "PUSCH", "SSB"])
        pdsch = next(r for r in res["rects"] if r["channel"] == "PDSCH")
        self.assertEqual((pdsch["record"], pdsch["t"], pdsch["t1"]), (2, 1700000000.0005, 1700000000.0015))
        self.assertEqual(res["anchors"], [[1700000000.0005, 12345]])
        self.assertEqual(self.store.meta["grid"]["slots_per_frame"], 10)
        self.assertEqual(self.source.grid(self.path, self.store, 0, 1, 1000)["rects"], [])

    def test_records(self):
        texts = [r["text"] for r in self.store.records(1, 10)]
        self.assertEqual(len(texts), 3)
        self.assertTrue(texts[0].endswith("CellStartEvent"))
        # slot_tx 12345 of 10 slots per frame.
        self.assertIn("slot=1234.5 latency=42us", texts[1])
        self.assertEqual(json.loads(self.source.record_detail(self.path, 3))["type"], "CellStopEvent")
        # The structure of the event too, which the record pane shows as tables.
        slot = self.source.record_data(self.path, 2)
        self.assertEqual((slot["type"], len(slot["inputs"]), len(slot["decision"]["ue_pdschs"])), ("CellSlotEvent", 4, 1))


class SlotTimesTest(unittest.TestCase):
    def test_slots_on_a_grid(self):
        # Timestamps that jitter around 1 ms slots, across an SFN wrap of 100 slots.
        slots = [(10.0001, 98), (10.0012, 99), (10.0019, 0), (10.0035, 1)]
        times = _slot_times(slots, 0.001, 100)
        steps = [round(b - a, 9) for a, b in zip(times, times[1:])]
        self.assertEqual(steps, [0.001, 0.001, 0.001])
        # At the median difference between the timestamps and the grid.
        self.assertAlmostEqual(times[0], 10.0002, places=6)
        self.assertEqual(_slot_times([], 0.001, 100), [])
