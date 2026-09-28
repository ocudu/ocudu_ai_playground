# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for mr_comments.py.

Run from the repo root:
    python3 -m unittest discover -s tests -p "test_*.py"
    python3 tests/code_review/test_mr_comments.py
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
SCRIPT = TEST_DIR.parents[1] / "skills" / "ocudu-code-review" / "scripts" / "mr_comments.py"


def note(body, author="rev", system=False, resolved=None, path=None, line=None):
    payload = {"body": body, "author": {"username": author}, "system": system}
    if resolved is not None:
        payload["resolved"] = resolved
    if path:
        payload["position"] = {"new_path": path, "new_line": line}
    return payload


class MrCommentsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "comments.md"

    def run_script(self, discussions, *extra):
        """Runs the script against a `glab` stub serving `discussions`."""
        bindir = Path(self.tmp.name) / "bin"
        bindir.mkdir(exist_ok=True)
        payload = json.dumps(discussions).replace("'", "'\\''")
        stub = bindir / "glab"
        stub.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            f"  *page=1*) printf '%s' '{payload}' ;;\n"
            "  *) printf '[]' ;;\n"
            "esac\n"
        )
        stub.chmod(0o755)
        return subprocess.run(
            [str(SCRIPT), "--project", "ocudu/ocudu", "--iid", "42",
             "--out", str(self.out), *extra],
            capture_output=True, text=True,
            env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"},
        )

    def keys(self, stdout, key):
        return [line[len(key) + 1:] for line in stdout.splitlines()
                if line.startswith(f"{key}=")]

    def test_diff_note_is_anchored_and_transcribed(self):
        result = self.run_script([
            {"notes": [note("Bounds check missing", author="ana",
                            path="lib/mac/mac_ul.cpp", line=88)]},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        comments = self.keys(result.stdout, "COMMENT")
        self.assertEqual(comments, ["lib/mac/mac_ul.cpp:88 @ana: Bounds check missing"])
        self.assertEqual(self.keys(result.stdout, "COMMENTS_FILE"), [str(self.out)])
        self.assertIn("Bounds check missing", self.out.read_text())

    def test_system_notes_are_dropped(self):
        result = self.run_script([
            {"notes": [note("added 3 commits", system=True)]},
            {"notes": [note("changed target branch", system=True)]},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.out.exists())

    def test_unresolved_threads_come_first_and_resolved_are_marked(self):
        result = self.run_script([
            {"notes": [note("Done already", resolved=True, path="a.cpp", line=1)]},
            {"notes": [note("Still open", resolved=False, path="b.cpp", line=2)]},
        ])
        comments = self.keys(result.stdout, "COMMENT")
        self.assertEqual(comments[0], "b.cpp:2 @rev: Still open")
        self.assertEqual(comments[1], "[resolved] a.cpp:1 @rev: Done already")

    def test_replies_are_counted_and_kept_verbatim(self):
        result = self.run_script([
            {"notes": [
                note("Why not a span?", author="ana", path="a.h", line=3),
                note("Because of\n\n```cpp\nint x;\n```", author="bo"),
            ]},
        ])
        self.assertIn("(+1 replies)", self.keys(result.stdout, "COMMENT")[0])
        transcript = self.out.read_text()
        self.assertIn("**@bo:**", transcript)
        self.assertIn("```cpp\nint x;\n```", transcript)

    def test_general_thread_has_no_anchor(self):
        result = self.run_script([{"notes": [note("Overall this looks fine")]}])
        self.assertEqual(self.keys(result.stdout, "COMMENT"),
                         ["general @rev: Overall this looks fine"])

    def test_long_bodies_are_truncated_only_in_the_compact_line(self):
        body = "x" * 500
        result = self.run_script([{"notes": [note(body, path="a.cpp", line=1)]}])
        compact = self.keys(result.stdout, "COMMENT")[0]
        self.assertLess(len(compact), 260)
        self.assertTrue(compact.endswith("…"))
        self.assertIn(body, self.out.read_text())

    def test_max_caps_the_compact_lines(self):
        discussions = [{"notes": [note(f"n{i}", path="a.cpp", line=i)]} for i in range(5)]
        result = self.run_script(discussions, "--max", "2")
        self.assertEqual(len(self.keys(result.stdout, "COMMENT")), 2)
        self.assertEqual(self.keys(result.stdout, "COMMENTS_MORE"), ["3"])
        self.assertEqual(self.out.read_text().count("## "), 5)

    def test_glab_failure_exits_two(self):
        bindir = Path(self.tmp.name) / "bin"
        bindir.mkdir(exist_ok=True)
        stub = bindir / "glab"
        stub.write_text("#!/bin/sh\necho 'no token' >&2\nexit 1\n")
        stub.chmod(0o755)
        result = subprocess.run(
            [str(SCRIPT), "--project", "ocudu/ocudu", "--iid", "42", "--out", str(self.out)],
            capture_output=True, text=True,
            env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("glab api failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
