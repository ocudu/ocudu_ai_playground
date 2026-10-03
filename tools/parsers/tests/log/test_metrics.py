# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest
from datetime import datetime

from parsers.log import metrics, preamble

SCHED_LINE = "2025-04-04T15:55:29.878489 [METRICS ] Scheduler cell pci=1 metrics: total_dl_brate=1.4Gbps total_ul_brate=99Mbps nof_prbs=273 nof_dl_slots=1600 nof_ul_slots=400 error_indications=0 pdsch_rbs_per_slot=271 pusch_rbs_per_slot=251 pdschs_per_slot=3 puschs_per_slot=2 failed_pdcch=0 failed_uci=30 nof_ues=32 mean_latency=58usec max_latency=492usec max_latency_slot=814.16 latency_hist=[742, 1098, 150, 3, 3, 2, 1, 0, 0, 1] max_crc_delay=3ms max_ce_delay=4ms max_pucch_harq_delay=2.5ms max_pusch_harq_delay=2.5ms"
MAC_LINE = "2025-04-04T15:37:27.599168 [METRICS ] MAC cell pci=1 metrics: nof_slots=2000 slot_duration=500usec nof_voluntary_context_switches=1 nof_involuntary_context_switches=261 wall_clock_latency=[avg=127usec max=533usec max_slot=132.16] dl_tti_req_latency=[avg=67usec max=337usec max_slot=108.16] tx_data_req_latency=[avg=51usec max=268usec max_slot=132.16] slot_ind_latency=[avg=7usec max=41usec max_slot=132.17]"
MAC_LINE_SLOTS = "2025-11-07T09:35:25.129220 [METRICS ] MAC cell pci=1 metrics: slots=[100.0, 200.0) nof_slots=2000 slot_duration=500usec nof_voluntary_context_switches=0 nof_involuntary_context_switches=209 wall_clock_latency=[avg=25usec max=274usec max_slot=171.6] sched_latency=[avg=13usec max=131usec max_slot=101.15] dl_tti_req_latency=[avg=12usec max=258usec max_slot=171.6] tx_data_req_latency=[avg=7usec max=24usec max_slot=104.3] ul_tti_req_latency=[avg=9usec max=125usec max_slot=198.19] slot_ind_dequeue_latency=[avg=28usec max=102usec max_slot=167.14] slot_ind_msg_time_diff=[avg=541usec max=2374usec max_slot=125.4]\n"
MAC_LINE_HFN = "2025-11-07T09:38:18.654757 [METRICS ] MAC cell pci=1 metrics: slots=[984.0, 60.0(+1 HFNs)) nof_slots=2000 slot_duration=500usec nof_voluntary_context_switches=0 nof_involuntary_context_switches=37793 wall_clock_latency=[avg=521usec max=61871usec max_slot=1021.13] sched_latency=[avg=459usec max=61851usec max_slot=1021.13] dl_tti_req_latency=[avg=55usec max=2033usec max_slot=985.12] tx_data_req_latency=[avg=10usec max=296usec max_slot=40.10] ul_tti_req_latency=[avg=52usec max=584usec max_slot=1020.18] slot_ind_dequeue_latency=[avg=58usec max=10865usec max_slot=1022.9] slot_ind_msg_time_diff=[avg=2385usec max=146932usec max_slot=6.5]"
UPPER_PHY_LINE = "2025-07-10T05:10:51.686748 [METRICS ] Upper PHY sector#0 metrics: PHY metrics: dl_processing_max_latency=569.3us dl_processing_max_slot=203.0 ul_processing_max_latency=1077.7us ul_processing_max_slot=160.19 ldpc_encoder_avg_latency=2.6us ldpc_encoder_max_latency=13.7us ldpc_decoder_avg_latency=53.4us ldpc_decoder_max_latency=384.5us ldpc_decoder_avg_nof_iter=1.6"
EXEC_LINE = '2025-04-23T13:52:12.765052 [METRICS ] [I] Executor metrics "slot_ind_exec#0": nof_executes=2001 nof_defers=0 enqueue_avg=6usec enqueue_max=615usec task_avg=35usec task_max=314usec nof_vol_ctxt_switch=31 nof_invol_ctxt_switch=16'
OFH_LINE = "2025-08-25T23:14:30.687135 [METRICS ] OFH metrics: timing metrics: nof_skipped_symbols=0 skipped_symbols_max_burst=0; sector#0 pci=1 received messages stats: rx_total=6800 rx_early=0 rx_on_time=6800 rx_late=0 earliest_msg_us=35.71 latest_msg_us=321.43, nof_missed_uplink_symbols=0 nof_missed_prach_occasions=0; ether_rx: cpu_usage=0.7% max_latency=2.62us avg_latency=0.48us throughput=695.75Mbps rx_bytes=86881600; ether_tx: cpu_usage=10.1% max_latency=6.25us avg_latency=1.09us throughput=5217.27Mbps tx_bytes=651506320; ecpri: nof_past_seqid_msg=0 nof_future_seqid_msg=0; rcv_prach: nof_dropped_msg=0 cpu_usage=0.2% max_latency=6.25us avg_latency=1.78us; rcv_ul: nof_dropped_msg=0 cpu_usage=3.5% max_latency=26.62us avg_latency=6.30us; tx_dl_up: cpu_usage=28.5% dl_up_max_latency=121.63us dl_up_avg_latency=44.43us; tx_dl_cp: cpu_usage=0.6% dl_cp_max_latency=10.50us dl_cp_avg_latency=0.90us; tx_ul_cp: cpu_usage=0.1% ul_cp_max_latency=4.09us ul_cp_avg_latency=0.84us; message_tx: cpu_usage=14.7% max_latency=27.52us avg_latency=5.23us; tx_kpis: nof_late_dl_rgs=0 nof_late_ul_req=0 nof_late_cp_dl=0 nof_late_up_dl=0 nof_late_cp_ul=0"


class ParseFieldsTest(unittest.TestCase):
    def test_sched_cell(self):
        fields = metrics.parse_fields(SCHED_LINE, "sched", preamble.match_preamble(SCHED_LINE))
        self.assertIsNotNone(fields)
        self.assertEqual(fields["timestamp"], (datetime.fromisoformat("2025-04-04T15:55:29.878489"), ""))
        self.assertEqual(fields["pci"], (1, ""))
        self.assertEqual(fields["nof_ues"], (32, ""))
        self.assertEqual(fields["total_dl_brate"], (1.4e9, "bps"))
        self.assertEqual(fields["total_ul_brate"], (99e6, "bps"))
        self.assertEqual(fields["max_crc_delay"], (3, "ms"))
        self.assertEqual(fields["latency_hist"], ([742, 1098, 150, 3, 3, 2, 1, 0, 0, 1], ""))

    def test_mac(self):
        fields = metrics.parse_fields(MAC_LINE, "mac")
        self.assertIsNotNone(fields)
        self.assertEqual(fields["timestamp"], (datetime.fromisoformat("2025-04-04T15:37:27.599168"), ""))
        self.assertEqual(fields["pci"], (1, ""))
        self.assertEqual(fields["wall_clock_latency_avg"], (127, "usec"))
        self.assertEqual(fields["dl_tti_req_latency_max"], (337, "usec"))

    def test_mac_with_slot_range(self):
        fields = metrics.parse_fields(MAC_LINE_SLOTS, "mac", preamble.match_preamble(MAC_LINE_SLOTS, "METRICS"))
        self.assertIsNotNone(fields)
        self.assertEqual(fields["slots"], ([100.0, 200.0], ""))
        self.assertEqual(fields["wall_clock_latency_max"], (274, "usec"))

    def test_mac_with_hfn_wrap(self):
        fields = metrics.parse_fields(MAC_LINE_HFN, "mac", preamble.match_preamble(MAC_LINE_HFN, "METRICS"))
        self.assertIsNotNone(fields)
        self.assertEqual(fields["nof_slots"], (2000, ""))
        self.assertEqual(fields["wall_clock_latency_max"], (61871, "usec"))

    def test_upper_phy(self):
        fields = metrics.parse_fields(UPPER_PHY_LINE, "upper_phy")
        self.assertEqual(fields["sector"], (0, ""))
        self.assertEqual(fields["ul_processing_max_latency"], (1077.7, "us"))

    def test_executor(self):
        fields = metrics.parse_fields(EXEC_LINE, "exec")
        self.assertEqual(fields["execname"], ("slot_ind_exec#0", ""))
        self.assertEqual(fields["task_max"], (314, "usec"))

    def test_ofh(self):
        fields = metrics.parse_fields(OFH_LINE, "ofh")
        self.assertEqual(fields["nof_skipped_symbols"], (0, ""))
        self.assertEqual(fields["ether_rx_max_latency"], (2.62, "us"))
        self.assertEqual(fields["ether_rx_cpu_usage"], (0.7, "%"))
        self.assertEqual(fields["ether_tx_throughput"], (5217.27e6, "bps"))

    def test_wrong_layer_returns_none(self):
        self.assertIsNone(metrics.parse_fields(SCHED_LINE, "mac"))

    def test_non_metrics_logger_returns_none(self):
        self.assertIsNone(metrics.parse_fields("2025-04-04T15:55:29.878489 [SCHED   ] [I] Scheduler cell pci=1 metrics: nof_ues=1", "sched"))


class ExtractMetricFieldsTest(unittest.TestCase):
    def test_values_and_sublists(self):
        fields = metrics.extract_metric_fields("total_dl_brate=1.4Gbps wall_clock_latency=[avg=127usec max=533usec max_slot=132.16]")
        self.assertEqual(fields["total_dl_brate"], (1.4e9, "bps"))
        self.assertEqual(fields["wall_clock_latency_max"], (533, "usec"))
        self.assertEqual(fields["wall_clock_latency_max_slot"], (132.16, ""))

    def test_single_element_list(self):
        self.assertEqual(metrics.extract_metric_fields("hist=[5]"), {"hist": ([5], "")})


if __name__ == "__main__":
    unittest.main()
