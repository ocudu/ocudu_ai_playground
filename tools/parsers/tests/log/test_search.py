# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest

from parsers.log import search

LOG = """\
2026-07-27T15:44:57.314934 [GNB     ] [I] Built in RelWithDebInfo mode using commit 404c93d34d on branch main
2026-07-27T15:44:57.315000 [CONFIG  ] [D] gNB input configuration (all values):
log:
  all_level: info

2026-07-27T15:45:01.100000 [RRC     ] [I] ue=0 c-rnti=0x4601: Tx DL-DCCH rrcReconfiguration
  rrcReconfiguration {
    reconfigurationWithSync
  }
2026-07-27T15:45:02.200000 [SCHED   ] [W] [  12.3] pci=1 rnti=0x4602: late HARQ
2026-07-27T15:45:03.300000 [METRICS ] Scheduler UE ue=1 pci=1 rnti=0x4602 metrics: dl_mcs=27
""".splitlines(keepends=True)


def found(flt, include_config_echo=False):
    return [entry.splitlines()[0][27:37] for entry in search.search(LOG, flt, include_config_echo)]


class SearchTest(unittest.TestCase):
    def test_entries(self):
        entries = list(search.entries(LOG))
        self.assertEqual(len(entries), 4)
        # The configuration echo is left out, and continuation lines are kept with their entry.
        self.assertEqual(entries[1][1:], ["  rrcReconfiguration {", "    reconfigurationWithSync", "  }"])
        self.assertEqual(len(list(search.entries(LOG, include_config_echo=True))), 5)

    def test_echo_of_other_nodes_is_left_out(self):
        header = "2026-07-27T15:44:57.315000 [CONFIG  ] [I] Input configuration (only non-default values):"
        self.assertEqual(len(list(search.entries([LOG[0], header, *LOG[2:]]))), 4)

    def test_filters(self):
        self.assertEqual(found(search.Filter(layer="rrc")), ["[RRC     ]"])
        self.assertEqual(found(search.Filter(level="W|E")), ["[SCHED   ]"])
        self.assertEqual(found(search.Filter(ue="1")), ["[METRICS ]"])
        self.assertEqual(found(search.Filter(rnti="4602")), ["[SCHED   ]", "[METRICS ]"])
        self.assertEqual(found(search.Filter(rnti="4601")), ["[RRC     ]"])
        self.assertEqual(found(search.Filter(pci="1", layer="SCHED")), ["[SCHED   ]"])

    def test_time_bounds(self):
        self.assertEqual(found(search.Filter(after="15:45:02", before="15:45:02.9")), ["[SCHED   ]"])
        self.assertEqual(found(search.Filter(after="2026-07-27T15:45:03")), ["[METRICS ]"])

    def test_pattern_in_body(self):
        self.assertEqual(found(search.Filter(pattern="^ *reconfigurationwithsync$")), ["[RRC     ]"])
        self.assertEqual(found(search.Filter(pattern="all_level"), include_config_echo=True), ["[CONFIG  ]"])
