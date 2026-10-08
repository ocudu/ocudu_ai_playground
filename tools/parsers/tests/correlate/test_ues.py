# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest

from parsers.correlate.ues import Context, combine

# F1AP UE contexts: a UE attaching at 10 s, handed over at 20 s to a new context with C-RNTI 17922 (0x4602).
F1AP = [
    Context("f1ap", 0, 10.0, 20.5, {"rnti": "17921", "du_f1ap": "0", "cu_f1ap": "0"}),
    Context("f1ap", 1, 20.0, 30.0, {"rnti": "17922", "du_f1ap": "1", "cu_f1ap": "1"}, open=True),
]
# UEs of a log: the first UE, the handover target created without RNTI, its contention-free random access with the
# RNTI only, and a UE of no F1AP context.
LOG = [
    Context("log", 0, 9.9, 20.5, {"ue": 0, "rnti": "0x4601"}),
    Context("log", 1, 20.001, 30.0, {"ue": 1, "rnti": None}),
    Context("log", 2, 20.1, 20.1, {"rnti": "0x4602"}),
    Context("log", 3, 50.0, 51.0, {"ue": 5, "rnti": "0x4609"}),
]


class CombineTest(unittest.TestCase):
    def test_f1ap_and_log(self):
        ues = combine(F1AP, LOG)
        self.assertEqual([(ue.key, ue.parts) for ue in ues], [
            ("f1ap:0", [("f1ap", 0), ("log", 0)]),
            ("f1ap:1", [("f1ap", 1), ("log", 1), ("log", 2)]),
            ("log:3", [("log", 3)]),
        ])
        first, target, own = ues
        # The log widens the lifetime of the UE, e.g. with the random access before the first F1AP message.
        self.assertEqual((first.t_start, first.ids), (9.9, {"rnti": ["0x4601"], "du_f1ap": ["0"], "cu_f1ap": ["0"], "ue": ["0"]}))
        self.assertEqual((target.first("ue"), target.first("rnti"), target.open), ("1", "0x4602", True))
        self.assertEqual(own.ids, {"ue": ["5"], "rnti": ["0x4609"]})

    def test_one_source(self):
        ues = combine(LOG)
        self.assertEqual([ue.key for ue in ues], ["log:0", "log:1", "log:2", "log:3"])
        self.assertIsNone(ues[1].first("rnti"))

    def test_rnti_outside_the_lifetime_does_not_join(self):
        late = [Context("log", 0, 40.0, 41.0, {"rnti": "0x4601"})]
        self.assertEqual([ue.key for ue in combine(F1AP, late)], ["f1ap:0", "f1ap:1", "log:0"])

    def test_contexts_of_one_source_do_not_join_each_other(self):
        log = [Context("log", 0, 10.0, 11.0, {"rnti": "0x4601"}), Context("log", 1, 10.5, 12.0, {"rnti": "0x4601"})]
        self.assertEqual(len(combine(log)), 2)
