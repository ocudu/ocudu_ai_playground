# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import json
import tempfile
import unittest
from pathlib import Path

from parsers.log import console, metrics_json, summary

LOG = """\
2026-07-27T15:44:57.314934 [GNB     ] [I] Built in RelWithDebInfo mode using commit 404c93d34d on branch main
2026-07-27T15:44:57.315000 [CONFIG  ] [D] gNB input configuration (all values):
log:
  all_level: info
2026-07-27T15:44:58.000000 [CU-CP   ] [I] Connection to AMF on 10.0.0.1:38412 was established
2026-07-27T15:44:58.100000 [NGAP    ] [I] Rx PDU: NGSetupResponse
2026-07-27T15:44:58.200000 [SCHED   ] [I] Cell creation idx=0, pci=1, plmn=00101
2026-07-27T15:45:00.000000 [SCHED   ] [I] [  10.1] Slot decisions pci=1 t=5us: prach(ra-rnti=0x10f)
2026-07-27T15:45:00.100000 [CU-CP   ] [I] ue=0 c-rnti=0x4601: UE created
2026-07-27T15:45:01.100000 [RRC     ] [I] ue=0 c-rnti=0x4601: Tx DL-DCCH rrcReconfiguration
2026-07-27T15:45:01.200000 [RRC     ] [I] ue=0 c-rnti=0x4601: Rx UL-DCCH rrcReconfigurationComplete
2026-07-27T15:45:01.300000 [CU-CP   ] [I] ue=0: "Initial Context Setup Routine" finished successfully
2026-07-27T15:45:01.400000 [CU-CP-E1] [I] Rx PDU: BearerContextSetupResponse
2026-07-27T15:45:02.000000 [MAC     ] [W] MAC UE creation (ue=0) took 2ms
2026-07-27T15:45:02.100000 [SCHED   ] [W] [  12.3] pci=1 rnti=0x4601: late HARQ
2026-07-27T15:45:02.200000 [PHY     ] [E] [  12.4] crc=KO
2026-07-27T15:45:03.000000 [METRICS ] Scheduler UE ue=0 pci=1 rnti=0x4601 metrics: dl_mcs=27
2026-07-27T15:45:04.000000 [CU-CP   ] [I] ue=0: "UE Removal Routine" finished successfully
2026-07-27T15:45:05.000000 [GNB     ] [I] Closing PCAP files...
2026-07-27T15:45:05.100000 [GNB     ] [I] Workers stopped successfully
""".splitlines(keepends=True)

STDOUT = """\
--== OCUDU gNB (commit 404c93d34d) ==--
Cell pci=1, bw=20 MHz, 1T1R, dl_arfcn=368500 (n3)
N2: Connection to AMF on 10.0.0.1:38412 completed
==== gNB started ===
          |--------------------DL---------------------|
 pci rnti | cqi  ri  mcs  brate   ok  nok  (%)  dl_bs |
   1 4601 |  15   1   27    10M  100    0   0%      0 |
   1 4601 |  15   1   27    12M  100    0   0%      0 |
Stopping...
"""


class SummaryTest(unittest.TestCase):
    def test_summarize(self):
        s = summary.summarize(LOG)
        self.assertEqual((s.build_commit, s.build_branch), ("404c93d34d", "main"))
        self.assertEqual((s.first_ts, s.last_ts), ("2026-07-27T15:44:57.314934", "2026-07-27T15:45:05.100000"))
        self.assertEqual((s.ng_setup, s.amf_connected_ts), ("success", "2026-07-27T15:44:58.000000"))
        self.assertEqual(s.cells_created, [("2026-07-27T15:44:58.200000", 1)])
        self.assertEqual(s.ue_creates, [("2026-07-27T15:45:00.100000", "0", "4601")])
        self.assertEqual((len(s.init_ctx_done), len(s.ue_releases)), (1, 1))
        self.assertEqual((s.rrc_reconfigs, s.prach_events, s.crc_fails, s.bearer_setups), (1, 1, 1, 1))
        self.assertEqual((s.benign_warning_count, [w[1] for w in s.warnings], [e[1] for e in s.errors]), (1, ["SCHED"], ["PHY"]))
        self.assertEqual((s.ues_seen, s.rntis_seen, s.pcis_seen), (["0"], ["4601"], [1]))
        self.assertEqual(len(s.rrc_msgs), 2)
        self.assertEqual((s.metrics_rows, s.clean_shutdown, s.shutdown_signal_ts), (1, True, "2026-07-27T15:45:05.000000"))

    def test_handovers(self):
        log = [
            "2026-07-27T15:45:01.100000 [RRC     ] [I] ue=0 c-rnti=0x4601: Tx DL-DCCH rrcReconfiguration\n",
            "{\n",
            '  "reconfigurationWithSync": {\n',
            "}\n",
            "2026-07-27T15:45:01.200000 [NGAP    ] [I] Tx PDU ue=0: HandoverRequired\n",
            "2026-07-27T15:45:01.300000 [NGAP    ] [I] Rx PDU ue=1: HandoverRequest\n",
            "2026-07-27T15:45:01.400000 [NGAP    ] [I] Tx PDU ue=1: HandoverRequestAcknowledge\n",
        ]
        s = summary.summarize(log)
        self.assertEqual((s.ho_count, s.ngap_handover_count), (1, 2))

    def test_console(self):
        c = console.summarize(STDOUT.splitlines(keepends=True))
        self.assertEqual(c.banner_commit, "404c93d34d")
        self.assertEqual(c.cells, ["Cell pci=1, bw=20 MHz, 1T1R, dl_arfcn=368500 (n3)"])
        self.assertEqual((c.amf_connected, c.started, c.stopped, c.metrics_rows), (True, True, True, 2))

    def test_metrics_json(self):
        records = [
            {"cells": [{"cell_metrics": {"late_dl_harqs": 1, "msg3_nof_ok": 2, "max_latency": 40},
                        "ue_list": [{"dl_brate": 1e6, "ul_brate": 2e5}], "event_list": [{"event_type": "ue_create"}]}]},
            {"cells": [{"cell_metrics": {"late_dl_harqs": 2, "msg3_nof_nok": 1, "max_latency": 30},
                        "ue_list": [{"dl_brate": 3e6, "ul_brate": None}]}]},
        ]
        r = metrics_json.rollup(records)
        self.assertEqual((r.records, r.late_dl_harqs, r.msg3_ok, r.msg3_nok, r.max_latency_us), (2, 3, 2, 1, 40))
        self.assertEqual((r.peak_dl_brate, r.peak_ul_brate, dict(r.event_counts)), (3e6, 2e5, {"ue_create": 1}))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "metrics.json"
            path.write_text(json.dumps(records))
            self.assertEqual(metrics_json.load_records(path), records)
            # A run killed while writing leaves the array unclosed, its complete lines still read.
            path.write_text("[\n" + ",\n".join(json.dumps(r) for r in records) + ",\n{\"cells\": [")
            self.assertEqual(metrics_json.load_records(path), records)
