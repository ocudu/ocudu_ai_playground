#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Smoke test for schedtrace_ue_metrics.py, which imports the parsers package of this repo through the symlink in
skills/analyze-ran-log/scripts/_lib. The metrics themselves are tested in tools/parsers/tests/schedtrace.

Usage:
    python3 test_schedtrace_ue_metrics.py
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parents[1]
SCRIPT = ROOT / "skills" / "analyze-ran-log" / "scripts" / "ocudu" / "schedtrace_ue_metrics.py"
# Trace of a cell start, a slot with grants and reports of UEs 0x4601 and 0x4602, and a cell stop.
TRACE = ROOT / "tools" / "parsers" / "tests" / "schedtrace" / "data" / "schedtrace_cell0.bin"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


class SchedtraceUeMetricsTest(unittest.TestCase):
    def test_summary_and_periods(self):
        res = run(str(TRACE), "-j", "2")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("slots=1", res.stdout)
        self.assertIn("0x4601", res.stdout)
        self.assertIn("0x4602", res.stdout)
        self.assertIn("dl_sched_Mbps", res.stdout)

    def test_ue_filter_and_grants(self):
        res = run(str(TRACE.parent), "--rnti", "17921", "--grants", "dl")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("12345", res.stdout)
        self.assertNotIn("0x4602", res.stdout)

    def test_window_without_slots(self):
        res = run(str(TRACE), "--after", "23:00")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("no slots in the window", res.stdout)

    def test_invalid_rnti(self):
        res = run(str(TRACE), "--rnti", "zz")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("invalid RNTI", res.stderr)


if __name__ == "__main__":
    unittest.main()
