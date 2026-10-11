# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest
from pathlib import Path

from parsers import schedtrace
from parsers.schedtrace import collisions, grid

DATA = Path(__file__).parent / "data"


def vrbs(start, length, hop=None):
    return {"type": "VrbAlloc", "vrb_start": start, "vrb_length": length, "vrb_second_hop_start": hop}


def pdsch(rnti, rbs, sym_start=2, sym_length=12):
    return {"rnti": rnti, "rbs": rbs, "sym_start": sym_start, "sym_length": sym_length, "codewords": [], "harq_id": 0,
            "ue_index": 0, "nof_retxs": 0, "k1": 4}


def pusch(rnti, rbs, sym_start=0, sym_length=14):
    return {"rnti": rnti, "rbs": rbs, "sym_start": sym_start, "sym_length": sym_length, "harq_id": 0, "tb_size_bytes": 0,
            "rv_index": 0, "nof_retxs": 0, "k2": 4, "ue_index": 0}


def pdcch(rnti, coreset_id, cce, aggr_lvl, dci_type=5):
    return {"rnti": rnti, "dci_type": dci_type, "coreset_id": coreset_id, "cce": cce, "aggr_lvl": aggr_lvl}


def slot(**decision):
    return {"type": "CellSlotEvent", "slot_tx": 7, "timestamp_us": 1, "decision": decision}


class CollisionsTest(unittest.TestCase):
    def setUp(self):
        start = next(schedtrace.read(DATA / "schedtrace_cell0.bin"))
        self.cell = grid.cell_of(start)

    def kinds(self, event):
        return [(c.kind, c.a["item"], c.b["item"], c.overlap) for c in collisions.slot_collisions(event, self.cell)]

    def test_pdschs(self):
        event = slot(ue_pdschs=[pdsch(1, vrbs(0, 10)), pdsch(2, vrbs(8, 4), sym_start=10, sym_length=4), pdsch(3, vrbs(20, 5))])
        # The DL BWP starts at CRB 2: VRBs 8 and 9 are CRBs 10 and 11, in symbols 10 to 13.
        self.assertEqual(self.kinds(event), [("PDSCH-PDSCH", ["ue_pdschs", 0], ["ue_pdschs", 1], [(10, 4, 10, 2)])])

    def test_pdschs_of_other_vrb_origins_are_not_compared(self):
        # The PDSCH of DCI format 1_0 counts its VRBs from its CORESET, whose CRBs the trace does not have.
        event = slot(ue_pdschs=[pdsch(1, vrbs(0, 2)), pdsch(2, vrbs(0, 2))],
                     dl_pdcchs=[pdcch(1, 0, 0, 2, dci_type=2), pdcch(2, 1, 0, 2)])
        self.assertEqual(self.kinds(event), [])
        event["decision"]["dl_pdcchs"][1] = pdcch(2, 0, 4, 2, dci_type=2)
        self.assertEqual([k[0] for k in self.kinds(event)], ["PDSCH-PDSCH"])

    def test_puschs_and_pucchs(self):
        # PUCCH resource 1: 2 PRBs at PRB 40 in symbol 12, hopping to PRB 7 in symbol 13.
        pucch = {"rnti": 3, "res_idx": 1, "nof_bits_harq_ack": 1, "nof_bits_sr": 0, "nof_bits_csi1": 0}
        event = slot(puschs=[pusch(1, vrbs(0, 10)), pusch(2, vrbs(9, 2)), pusch(4, vrbs(48, 2))], pucchs=[pucch])
        # The UL BWP starts at CRB 0.
        self.assertEqual(self.kinds(event), [
            ("PUSCH-PUSCH", ["puschs", 0], ["puschs", 1], [(0, 14, 9, 1)]),
            ("PUSCH-PUCCH", ["puschs", 0], ["pucchs", 0], [(13, 1, 7, 2)]),
        ])

    def test_frequency_hops_of_one_allocation_do_not_collide(self):
        event = slot(puschs=[pusch(1, vrbs(0, 4, hop=2))])
        self.assertEqual(self.kinds(event), [])

    def test_pdcchs(self):
        # Aggregation level 2 is 4 CCEs: 0 to 3 and 2 to 5 share 2 and 3, in CORESET 1 only.
        event = slot(dl_pdcchs=[pdcch(1, 1, 0, 2), pdcch(2, 0, 2, 2)], ul_pdcchs=[pdcch(3, 1, 2, 2), pdcch(4, 1, 6, 0)])
        self.assertEqual(self.kinds(event), [("PDCCH-PDCCH", ["dl_pdcchs", 0], ["ul_pdcchs", 0], [(2, 2)])])

    def test_find(self):
        self.assertEqual(list(collisions.find(DATA / "schedtrace_cell0.bin")), [])
