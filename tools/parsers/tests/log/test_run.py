# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import tempfile
import unittest
from pathlib import Path

from parsers.log import run

BUILD_LINE = "{} [GNB     ] [I] Built in RelWithDebInfo mode using commit 17217212e8 on branch {}\n"


def write_log(path: Path, start: str, end: str, branch: str = "fix_cfra") -> Path:
    path.write_text(
        BUILD_LINE.format(start, branch)
        + f"{start} [CONFIG  ] [D] Input configuration (all values):\n"
        + "  log:\n"
        + f"{end} [GNB     ] [I] Workers stopped successfully\n"
    )
    return path


class LogRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_log_run(self):
        r = run.log_run(write_log(self.dir / "gnb.log", "2026-05-15T12:24:29.377170", "2026-05-15T12:25:10.000000"))
        self.assertEqual((r.mode, r.commit, r.branch), ("RelWithDebInfo", "17217212e8", "fix_cfra"))
        self.assertAlmostEqual(r.end - r.start, 40.62283, places=5)

    def test_not_a_run_log(self):
        path = self.dir / "ue.log"
        path.write_text("# lteue version 2026-05-13\n")
        self.assertIsNone(run.log_run(path))
        self.assertIsNone(run.log_run(self.dir / "missing.log"))

    def test_same_run(self):
        du = run.log_run(write_log(self.dir / "du.log", "2026-05-15T12:24:29.000000", "2026-05-15T12:30:00.000000"))
        cu = run.log_run(write_log(self.dir / "cu.log", "2026-05-15T12:24:20.000000", "2026-05-15T12:30:05.000000"))
        later = run.log_run(write_log(self.dir / "later.log", "2026-05-15T13:00:00.000000", "2026-05-15T13:05:00.000000"))
        other = run.log_run(write_log(self.dir / "other.log", "2026-05-15T12:24:29.000000", "2026-05-15T12:30:00.000000", "dev"))
        self.assertTrue(run.same_run(du, cu))
        self.assertFalse(run.same_run(du, later))
        self.assertFalse(run.same_run(du, other))


if __name__ == "__main__":
    unittest.main()
