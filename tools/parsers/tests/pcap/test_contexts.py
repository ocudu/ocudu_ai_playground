# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest

from parsers.pcap.contexts import ContextTracker, ue_contexts


def msg(epoch, code, outcome="initiating", du=None, cu=None, crnti=None):
    return {"epoch": epoch, "code": code, "outcome": outcome, "du_ue_f1ap_id": du, "cu_ue_f1ap_id": cu, "crnti": crnti}


class ContextTrackerTest(unittest.TestCase):
    def test_f1ap(self):
        msgs = [
            msg(1.0, "1"),
            # InitialULRRCMessageTransfer, with the DU id and the C-RNTI only, then the CU id.
            msg(2.0, "11", du="0", crnti="17921"),
            msg(2.1, "13", du="0", cu="5"),
            msg(3.0, "6", "successful", du="0", cu="5"),
            # The DU id is free again for a later UE.
            msg(4.0, "11", du="0", crnti="17922"),
        ]
        tracker = ContextTracker("f1ap")
        self.assertEqual([c.id if (c := tracker.assign(m)) else None for m in msgs], [None, 0, 0, 0, 1])
        first, second = tracker.contexts
        self.assertEqual((first.t_start, first.t_end, first.rnti, first.released), (2.0, 3.0, "0x4601", True))
        self.assertEqual(first.label(), "du_f1ap=0 cu_f1ap=5")
        self.assertEqual((second.ids, second.rnti, second.released), ({"du_f1ap": "0"}, "0x4602", False))

    def test_ue_contexts(self):
        self.assertEqual(len(ue_contexts("f1ap", [msg(1.0, "11", du="0"), msg(2.0, "11", du="1")])), 2)
