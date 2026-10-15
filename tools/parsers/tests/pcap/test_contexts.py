# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest

from parsers.pcap import messages
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

    def test_old_du_id_of_a_reestablishment(self):
        # The DLRRCMessageTransfer of an rrcReestablishment names the old gNB-DU UE F1AP ID after the UE's own.
        row = dict.fromkeys(messages.fields("f1ap"), "")
        row.update({"frame.number": "3", "frame.time_epoch": "2.5", "f1ap.procedureCode": "12",
                    "f1ap.GNB_DU_UE_F1AP_ID": "7,3", "f1ap.GNB_CU_UE_F1AP_ID": "7"})
        reest = {**messages.message("f1ap", row), "crnti": None}
        self.assertEqual(reest["du_ue_f1ap_id"], "7")
        self.assertEqual(reest["old_du_ue_f1ap_id"], "3")
        # A Reset lists the ids of several UEs, none of them old.
        reset = messages.message("f1ap", {**row, "f1ap.procedureCode": "0"})
        self.assertIsNone(reset["old_du_ue_f1ap_id"])
        tracker = ContextTracker("f1ap")
        # The old context, connected and silent since 1.1 s, then the reestablishment request of the new one.
        msgs = (msg(1.0, "11", du="3", crnti="17920"), msg(1.1, "13", du="3", cu="3"), msg(2.0, "11", du="7", crnti="17921"),
                reest, msg(2.6, "13", du="7", cu="7"))
        self.assertEqual([c.id for m in msgs if (c := tracker.assign(m))], [0, 0, 1, 1, 1])
        old, new = tracker.contexts
        # The reestablishment releases the old context, whose identifiers are free again.
        self.assertEqual((old.released, old.t_end, new.released), (True, 2.5, False))
        self.assertEqual(tracker.assign(msg(3.0, "11", du="3", crnti="17922")).id, 2)

    def test_ue_contexts(self):
        self.assertEqual(len(ue_contexts("f1ap", [msg(1.0, "11", du="0"), msg(2.0, "11", du="1")])), 2)

    def test_links(self):
        tracker = ContextTracker("ngap")
        msgs = [
            {"epoch": 1.0, "code": "15", "outcome": "initiating", "ran_ue_ngap_id": "0", "amf_ue_ngap_id": None, "links": {"nas": ["7E0041"]}},
            # The UPF TEID of a PDU session setup request, and the TEID of the gNB in its response, which is not one.
            {"epoch": 2.0, "code": "29", "outcome": "initiating", "ran_ue_ngap_id": "0", "amf_ue_ngap_id": "100", "links": {"teid": ["38F10041"]}},
            {"epoch": 2.1, "code": "29", "outcome": "successful", "ran_ue_ngap_id": "0", "amf_ue_ngap_id": "100", "links": {"teid": ["00000001"]}},
            {"epoch": 3.0, "code": "13", "outcome": "successful", "ran_ue_ngap_id": "0", "amf_ue_ngap_id": "100", "links": {"ho_rnti": ["17922"]}},
        ]
        for m in msgs:
            tracker.assign(m)
        links = tracker.contexts[0].links
        self.assertEqual(set(links), {"nas", "teid", "ho_rnti"})
        self.assertEqual((len(next(iter(links["nas"]))), links["teid"], links["ho_rnti"]), (16, {"38f10041": 2.0}, {"0x4602": 3.0}))
