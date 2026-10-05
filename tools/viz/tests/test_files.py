# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import os
import tempfile
import unittest
from pathlib import Path

from viz.files import PathNotAllowed, list_dir, resolve_within


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.root = base / "root"
        self.outside = base / "outside"
        (self.root / "logs" / "run1").mkdir(parents=True)
        self.outside.mkdir()
        (self.root / "logs" / "gnb.log").write_text("x" * 10)
        (self.root / "logs" / ".hidden").write_text("")
        (self.root / "logs" / "B.txt").write_text("")
        (self.outside / "secret.log").write_text("")
        os.symlink(self.outside / "secret.log", self.root / "logs" / "link.log")
        os.symlink(self.outside, self.root / "out")

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolve_within_roots(self):
        self.assertEqual(resolve_within(self.root / "logs" / "gnb.log", [self.root]), self.root / "logs" / "gnb.log")

    def test_rejects_paths_outside_roots(self):
        for path in [
            self.outside / "secret.log",
            self.root / "logs" / "link.log",
            self.root / "out" / "secret.log",
            self.root / "logs" / ".." / ".." / "outside" / "secret.log",
            self.root / "missing.log",
            "relative/gnb.log",
        ]:
            with self.subTest(path=str(path)):
                with self.assertRaises(PathNotAllowed):
                    resolve_within(path, [self.root])

    def test_list_dir(self):
        res = list_dir(self.root / "logs", [self.root])
        self.assertEqual([(e["name"], e["type"]) for e in res["entries"]], [("run1", "dir"), ("B.txt", "file"), ("gnb.log", "file"), ("link.log", "file")])
        self.assertEqual(res["entries"][2]["size"], 10)
        self.assertEqual(res["parent"], str(self.root))
        self.assertIn(".hidden", [e["name"] for e in list_dir(self.root / "logs", [self.root], show_hidden=True)["entries"]])

    def test_list_root_has_no_parent(self):
        self.assertIsNone(list_dir(self.root, [self.root])["parent"])

    def test_list_rejects_files_and_outside(self):
        with self.assertRaises(PathNotAllowed):
            list_dir(self.root / "logs" / "gnb.log", [self.root])
        with self.assertRaises(PathNotAllowed):
            list_dir(self.outside, [self.root])


if __name__ == "__main__":
    unittest.main()
