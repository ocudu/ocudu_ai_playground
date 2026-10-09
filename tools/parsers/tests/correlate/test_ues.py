# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest

from parsers.correlate.ues import Context, combine, ue_traces

# F1AP UE contexts: a UE attaching at 10 s, handed over at 20 s to a new context with C-RNTI 17922 (0x4602).
F1AP = [
    Context("f1ap", 0, 10.0, 20.5, {"rnti": "17921", "du_f1ap": "0", "cu_f1ap": "0"}),
    Context("f1ap", 1, 20.0, 30.0, {"rnti": "17922", "du_f1ap": "1", "cu_f1ap": "1"}, open=True),
]
# UEs of a log: the first UE, the handover target created without RNTI, its contention-free random access with the
# RNTI only, and a UE of no F1AP context.
LOG = [
    Context("log", 0, 9.9, 20.5, {"du_ue": 0, "rnti": "0x4601"}),
    Context("log", 1, 20.001, 30.0, {"du_ue": 1, "rnti": None}),
    Context("log", 2, 20.1, 20.1, {"rnti": "0x4602"}),
    Context("log", 3, 50.0, 51.0, {"du_ue": 5, "rnti": "0x4609"}),
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
        self.assertEqual((first.t_start, first.ids), (9.9, {"rnti": ["0x4601"], "du_f1ap": ["0"], "cu_f1ap": ["0"], "du_ue": ["0"]}))
        self.assertEqual((target.first("du_ue"), target.first("rnti"), target.open), ("1", "0x4602", True))
        self.assertEqual(own.ids, {"du_ue": ["5"], "rnti": ["0x4609"]})

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


class UeTracesTest(unittest.TestCase):
    def test_handover_chain_and_core_contexts(self):
        f1ap = [
            # A UE attaching, with its NAS PDU, then handed over at 20 s to the context of C-RNTI 0x4602.
            Context("f1ap", 0, 10.0, 20.5, {"rnti": "0x4601", "cu_f1ap": "0"}, links={"nas": {"n1": 10.1}, "ho_rnti": {"0x4602": 20.0}}),
            Context("f1ap", 1, 20.0, 30.0, {"rnti": "0x4602", "cu_f1ap": "1"}),
            # Another UE, whose RNTI another cell reused: named by no handover near its creation.
            Context("f1ap", 2, 40.0, 41.0, {"rnti": "0x4602", "cu_f1ap": "2"}, links={"nas": {"n2": 40.1}}),
        ]
        cores = [
            Context("ngap", 0, 10.1, 30.0, {"ran_ngap": "0", "amf_ngap": "100"}, links={"nas": {"n1": 10.1}, "teid": {"t1": 10.2}}),
            Context("ngap", 1, 40.1, 41.0, {"ran_ngap": "1", "amf_ngap": "101"}, links={"nas": {"n2": 40.1}, "teid": {"t1": 40.2}}),
            # The E1AP contexts of the same UPF TEID, which the core reuses, join the NGAP one of the nearest message.
            Context("e1ap", 0, 10.3, 30.0, {"cu_cp_e1ap": "0"}, links={"teid": {"t1": 10.3}}),
            Context("e1ap", 1, 40.3, 41.0, {"cu_cp_e1ap": "1"}, links={"teid": {"t1": 40.3}}),
        ]
        ues = combine(f1ap)
        result = ue_traces(ues, cores)
        self.assertEqual([(t.ues, t.cores) for t in result], [
            (["f1ap:0", "f1ap:1"], [("ngap", 0), ("e1ap", 0)]),
            (["f1ap:2"], [("ngap", 1), ("e1ap", 1)]),
        ])
        self.assertEqual(result[0].ids["rnti"], ["0x4601", "0x4602"])
        # Each UE context gets its trace and the identifiers of its NGAP and E1AP contexts.
        self.assertEqual({k: ues[1].ids[k] for k in ("ue_trace", "ran_ngap", "cu_cp_e1ap")}, {"ue_trace": ["0"], "ran_ngap": ["0"], "cu_cp_e1ap": ["0"]})

    def test_reestablishment_and_cu_ue(self):
        f1ap = [
            Context("f1ap", 0, 10.0, 15.0, {"rnti": "0x4601"}),
            # Reestablishes the context of 0x4601.
            Context("f1ap", 1, 14.0, 20.0, {"rnti": "0x4603"}, links={"reest_rnti": {"0x4601": 14.0}}),
            # Same CU-CP UE index as the first, overlapping it, and a later UE reusing the index.
            Context("f1ap", 2, 12.0, 13.0, {"rnti": "0x4605", "cu_ue": "7"}),
            Context("f1ap", 3, 30.0, 31.0, {"rnti": "0x4606", "cu_ue": "7"}),
        ]
        logs = [Context("log", 0, 10.0, 15.0, {"rnti": "0x4601", "cu_ue": "7"})]
        ues = combine(f1ap, logs)
        self.assertEqual([t.ues for t in ue_traces(ues)], [["f1ap:0", "f1ap:2", "f1ap:1"], ["f1ap:3"]])
