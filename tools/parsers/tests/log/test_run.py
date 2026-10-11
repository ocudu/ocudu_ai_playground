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


class RunDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_dir_with_log(self):
        (self.dir / "du.log").write_text("")
        (self.dir / "gnb.log").write_text("")
        self.assertEqual(run.primary_log_in(self.dir), self.dir / "gnb.log")
        self.assertEqual(run.find_log(self.dir), (self.dir / "gnb.log"))

    def test_latest_run_under_component_dir(self):
        for name in ("2026-01-01_10-00-00", "2026-01-02_10-00-00"):
            (self.dir / "ocudu-gnb-1" / name).mkdir(parents=True)
            (self.dir / "ocudu-gnb-1" / name / "gnb.log").write_text("")
        latest = (self.dir / "ocudu-gnb-1" / "2026-01-02_10-00-00").resolve()
        self.assertEqual(run.resolve_run_dir(self.dir), latest)
        self.assertEqual(run.find_log(self.dir), latest / "gnb.log")

    def test_any_file_is_its_own_log(self):
        log = self.dir / "srsdu (1).log"
        log.write_text("")
        self.assertEqual(run.find_log(log), log.resolve())

    def test_no_log(self):
        with self.assertRaises(FileNotFoundError):
            run.find_log(self.dir)
