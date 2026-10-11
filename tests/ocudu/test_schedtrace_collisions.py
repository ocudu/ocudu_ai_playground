#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Smoke test for schedtrace_collisions.py, which imports the parsers package of this repo through the symlink in
skills/analyze-ran-log/scripts/_lib. The detection itself is tested in tools/parsers/tests/schedtrace.

Usage:
    python3 test_schedtrace_collisions.py
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parents[1]
SCRIPT = ROOT / "skills" / "analyze-ran-log" / "scripts" / "ocudu" / "schedtrace_collisions.py"
# Trace of a cell start, a slot and a cell stop, without collisions.
TRACE = ROOT / "tools" / "parsers" / "tests" / "schedtrace" / "data" / "schedtrace_cell0.bin"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


class SchedtraceCollisionsTest(unittest.TestCase):
    def test_trace(self):
        res = run(str(TRACE), "-j", "2")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("schedtrace_cell0.bin: 0 collisions", res.stdout)

    def test_directory(self):
        res = run(str(TRACE.parent), "--summary")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("0 collisions", res.stdout)

    def test_unknown_kind(self):
        res = run(str(TRACE), "--kinds", "PUSCH-PDSCH")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("unknown kinds", res.stderr)


if __name__ == "__main__":
    unittest.main()
