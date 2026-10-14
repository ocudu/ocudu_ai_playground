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
        self.assertIsNone(preamble.match_preamble("plmns: [00101]"))


class HeaderTest(unittest.TestCase):
    def test_header_ends_at_the_message(self):
        line = "2026-07-27T15:44:57.314934 [SCHED   ] [I] [  123.14] Slot decisions"
        m = preamble.match_header(line)
        self.assertEqual((m.group("timestamp"), m.group("layer"), m.group("level")), ("2026-07-27T15:44:57.314934", "SCHED", "I"))
        self.assertEqual(line[m.end() :], "[  123.14] Slot decisions")
        m = preamble.match_header("2025-04-04T15:55:29.878489 [METRICS ] Scheduler cell pci=1 metrics:")
        self.assertEqual((m.group("layer"), m.group("level")), ("METRICS", None))
        self.assertIsNone(preamble.match_header("plmns: [00101]"))

    def test_epoch(self):
        self.assertEqual(preamble.to_epoch("1970-01-01T00:00:01.500000"), 1.5)
        # An exact integer of microseconds.
        self.assertEqual(preamble.to_epoch_us("2026-04-21T03:21:49.089871"), 1776741709089871)
        self.assertIsNone(preamble.to_epoch("2026-04-21T03:21:49.08987x"))
        self.assertIsNone(preamble.to_epoch_us("plmns:"))

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
