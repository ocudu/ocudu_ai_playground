# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest

from parsers.log import procedures

# Real proc= lines, shortened, of two UE creations, the second without its opening stage.
LOG = """\
2026-04-21T03:21:49.089870 [DU-MNG  ] [I] ue=0 rnti=0x4601 proc="UE Create": Procedure started....
2026-04-21T03:21:49.090373 [MAC     ] [D] [   805.4] ue=0 crnti=0x4601 proc="MAC UE Creation": started...
2026-04-21T03:21:49.090404 [MAC     ] [D] [   805.4] ue=0 crnti=0x4601 proc="MAC UE Creation": MAC UE UL context created successfully.
2026-04-21T03:21:49.090412 [MAC     ] [D] [   805.4] ue=0 crnti=0x4601 proc="MAC UE Creation": UE DL context created successfully
2026-04-21T03:21:49.090900 [MAC     ] [D] [   805.5] ue=0 crnti=0x4601 proc="MAC UE Creation": UE context created successfully
2026-04-21T03:21:49.091047 [MAC     ] [I] [   805.6] ue=0 crnti=0x4601 proc="MAC UE Creation": finished successfully
2026-04-21T03:21:49.091051 [DU-MNG  ] [I] ue=0 rnti=0x4601 proc="UE Create": Procedure finished successfully.
2026-04-21T03:21:49.370377 [CU-CP-F1] [D] ue=0 du_ue=0 cu_ue=0 proc="UE Context Setup Procedure": UE context found
2026-04-21T23:59:59.999000 [DU-MNG  ] [I] ue=1 rnti=0x4602 proc="UE Create": Created DU UE context.
2026-04-22T00:00:00.001000 [DU-MNG  ] [I] ue=1 rnti=0x4602 proc="UE Create": Procedure finished successfully.
2026-04-22T00:00:01.000000 [DU-MNG  ] [I] ue=2 rnti=0x4603 proc="UE Delete": Procedure started....
""".splitlines(keepends=True)


class ProceduresTest(unittest.TestCase):
    def setUp(self):
        self.found = procedures.instances(LOG)

    def test_instances(self):
        creates = self.found["UE Create"]
        self.assertEqual([i.ue for i in creates], [0, 1])
        self.assertEqual(set(creates[0].stages), {"start", "done"})
        # The second opens at its first stage logged, across midnight.
        self.assertEqual(creates[1].stages["done"] - creates[1].stages["ctxt"], 2000)
        # Left open at the end of the log.
        self.assertEqual(self.found["UE Delete"], [])

    def test_latencies(self):
        mac = self.found["MAC UE Creation"]
        self.assertEqual(procedures.latencies(mac, "start", "done"), [674])
        # From the last of the UL and DL contexts, the DL one with its label of older builds.
        self.assertEqual(procedures.latencies(mac, ("ul", "dl"), "ctx"), [488])
        self.assertEqual(procedures.latencies(self.found["UE Create"], "start", "done"), [1181])

    def test_transitions(self):
        self.assertEqual(procedures.transitions("UE Delete"),
                         [("start -> done", "start", "done"), ("== TOTAL (start->done)", "start", "done")])
        self.assertEqual(procedures.transitions("MAC UE Creation")[2], ("ctx ready -> ctx created", ("ul", "dl"), "ctx"))

    def test_stats(self):
        st = procedures.stats(list(range(1, 101)))
        self.assertEqual((st.n, st.mean, st.p50, st.p90, st.p99, st.max), (100, 50.5, 50, 90, 99, 100))
        self.assertIsNone(procedures.stats([]))
