# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import contextlib
import io
import unittest

from viz.cli import _Progress


class ProgressTest(unittest.TestCase):
    def test_one_line_for_all_files(self):
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            progress = _Progress(["gnb.log", "f1ap.pcap"])
            progress.reporter(1)(10, 10)
            progress.reporter(0)(5, 10)
            progress.finish()
        lines = [line.strip() for line in out.getvalue().split("\r") if line.strip()]
        self.assertEqual(lines, [
            "Parsing 2 file(s): 1 done, gnb.log 0%",
            "Parsing 2 file(s): 1 done, gnb.log 50%",
            "Parsing 2 file(s): 2 done",
        ])
        self.assertTrue(out.getvalue().endswith("\n"))


if __name__ == "__main__":
    unittest.main()
