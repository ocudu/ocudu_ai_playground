# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest

from parsers.log import preamble


class MatchPreambleTest(unittest.TestCase):
    def test_full_preamble(self):
        m = preamble.match_preamble("2026-07-27T15:44:57.314934 [SCHED   ] [I] [  123.14] Slot decisions")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("timestamp"), "2026-07-27T15:44:57.314934")
        self.assertEqual(m.group("layer"), "SCHED")
        self.assertEqual(m.group("level"), "I")
        self.assertEqual(m.group("sfn"), "123")
        self.assertEqual(m.group("slot_index"), "14")

    def test_without_level_and_slot(self):
        m = preamble.match_preamble("2025-04-04T15:55:29.878489 [METRICS ] Scheduler cell pci=1 metrics:")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("layer"), "METRICS")
        self.assertIsNone(m.group("level"))
        self.assertIsNone(m.group("sfn"))

    def test_layer_filter(self):
        line = "2025-04-04T15:55:29.878489 [METRICS ] foo"
        self.assertIsNotNone(preamble.match_preamble(line, "METRICS"))
        self.assertIsNone(preamble.match_preamble(line, "SCHED"))

    def test_no_preamble(self):
        self.assertIsNone(preamble.match_preamble("  continuation line"))


class TokenizeMultilineLogsTest(unittest.TestCase):
    def test_groups_continuation_lines(self):
        lines = [
            "orphan line\n",
            "2026-07-27T15:44:57.314934 [SCHED   ] [I] [  123.14] Slot decisions:\n",
            "  - DL PDCCH: rnti=0x4601\n",
            "2026-07-27T15:44:57.315000 [MAC     ] [D] [  123.15] next\n",
        ]
        entries = list(preamble.tokenize_multiline_logs(lines))
        self.assertEqual(len(entries), 3)
        self.assertIsNone(entries[0][0])
        self.assertEqual(entries[0][1], ["orphan line\n"])
        self.assertEqual(entries[1][0].group("layer"), "SCHED")
        self.assertEqual(entries[1][1], lines[1:3])
        self.assertEqual(entries[2][1], lines[3:])


if __name__ == "__main__":
    unittest.main()
