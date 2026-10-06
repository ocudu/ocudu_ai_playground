# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import multiprocessing
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from parsers.log import chunks, metrics

from .test_metrics import SCHED_UE_LINE, SCHED_UE_LINE_NA


def write_log(path: Path, nof_seconds: int = 200) -> Path:
    """Synthetic log with metrics lines and debug entries continued on the next lines, one second apart."""
    lines = []
    for s in range(nof_seconds):
        ts = f"2026-06-29T14:{10 + s // 60:02d}:{s % 60:02d}.000000"
        lines.append(f"{ts} [SCHED   ] [D] [  {s}.0] Processed slot events pci=1:")
        lines.append("- PRACH: slot=3.9 preamble=1 ra-rnti=0x10b temp_crnti=0x4601 ta_cmd=0")
        lines.append("- PRACH: slot=3.9 preamble=2 ra-rnti=0x10b temp_crnti=0x4602 ta_cmd=0")
        lines.append(ts + (SCHED_UE_LINE if s % 2 else SCHED_UE_LINE_NA)[len(ts):])
    path.write_text("\n".join(lines) + "\n")
    return path


class ChunksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = write_log(self.dir / "gnb.log")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ranges_start_at_entries(self):
        text = self.log.read_bytes()
        ranges = chunks.chunk_ranges(self.log, 100)
        self.assertGreater(len(ranges), 50)
        self.assertEqual((ranges[0][0], ranges[-1][1]), (0, len(text)))
        for (_, end), (start, _) in zip(ranges, ranges[1:]):
            self.assertEqual(end, start)
            self.assertRegex(text[start : start + 30].decode(), r"^\d{4}-\d\d-\d\dT")

    def test_small_files(self):
        empty = self.dir / "empty.log"
        empty.write_bytes(b"")
        self.assertEqual(chunks.chunk_ranges(empty, 8), [(0, 0)])
        self.assertEqual(chunks.chunk_ranges(self.log, 1), [(0, self.log.stat().st_size)])

    def test_first_lines_and_read_lines(self):
        ranges = chunks.chunk_ranges(self.log, 20)
        firsts = chunks.first_lines(self.log, ranges)
        all_lines = self.log.read_bytes().split(b"\n")[:-1]
        self.assertEqual(firsts[0], 1)
        for (start, end), first in zip(ranges, firsts):
            lines = chunks.read_lines(self.log, start, end)
            self.assertEqual(lines, all_lines[first - 1 : first - 1 + len(lines)])

    def test_parse_file_in_parallel_matches_a_single_pass(self):
        serial = metrics.MetricsParser()
        expected = list(serial.parse_file(self.log))
        self.assertEqual([n for n, _ in expected[:2]], [4, 8])
        parallel = metrics.MetricsParser()
        with ProcessPoolExecutor(2, mp_context=multiprocessing.get_context("forkserver")) as executor:
            got = list(parallel.parse_file(self.log, executor, nof_chunks=7))
        self.assertEqual(got, expected)
        self.assertEqual(parallel.units, serial.units)


if __name__ == "__main__":
    unittest.main()
