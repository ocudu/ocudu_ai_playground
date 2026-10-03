# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import importlib.util
import unittest
from datetime import datetime

from parsers.log import metrics

# Real gnb.log lines, unless marked synthetic. Synthetic lines follow the OCUDU format strings.
DU_MANAGER_LINE = "2026-06-29T14:10:11.345162 [METRICS ] DU manager metrics: nof_ue_creations=106 avg_ue_creation_latency=16211usec max_ue_creation_latency=82651usec"
MAC_LINE = "2026-06-29T14:10:06.324561 [METRICS ] MAC cell pci=1 metrics: slots=[853.19, 864.0) nof_slots=201 slot_duration=500usec nof_voluntary_context_switches=0 nof_involuntary_context_switches=0 wall_clock_latency=[avg=7usec max=88usec max_slot=853.19] sched_latency=[avg=4usec max=61usec max_slot=853.19] dl_tti_req_latency=[avg=3usec max=79usec max_slot=856.2] tx_data_req_latency=[avg=0usec max=0usec max_slot=0.0] ul_tti_req_latency=[avg=2usec max=25usec max_slot=853.19] slot_ind_dequeue_latency=[avg=15usec max=42usec max_slot=856.14] slot_ind_msg_time_diff=[avg=500usec max=505usec max_slot=855.9]"
MAC_LINE_HFN = "2026-06-29T14:10:08.324570 [METRICS ] MAC cell pci=1 metrics: slots=[964.0, 40.0(+1 HFNs)) nof_slots=2000 slot_duration=500usec nof_voluntary_context_switches=0 nof_involuntary_context_switches=0 wall_clock_latency=[avg=4usec max=63usec max_slot=16.1] sched_latency=[avg=3usec max=11usec max_slot=6.3] dl_tti_req_latency=[avg=1usec max=57usec max_slot=16.1] tx_data_req_latency=[avg=4usec max=7usec max_slot=32.1] ul_tti_req_latency=[avg=1usec max=6usec max_slot=1007.19] slot_ind_dequeue_latency=[avg=15usec max=47usec max_slot=1003.5] slot_ind_msg_time_diff=[avg=500usec max=506usec max_slot=1014.2]"
# Events list trimmed to two entries.
SCHED_LINE = "2026-06-29T14:10:11.345195 [METRICS ] Scheduler cell pci=1 metrics: total_dl_brate=996kbps total_ul_brate=2.60Mbps nof_prbs=273 nof_dl_slots=1400 nof_ul_slots=600 nof_prach_preambles=133 error_indications=0 pdsch_rbs_per_slot=8 pusch_rbs_per_slot=9 pdschs_per_slot=1.08 puschs_per_slot=1.42 failed_dl_pdcch=91 failed_common_dl_pdcch=91 failed_ul_pdcch=90 failed_common_ul_pdcch=90 failed_uci=0 nof_ues=106 mean_latency=17usec max_latency=120usec max_latency_slot=332.4 latency_hist=[1864, 132, 4, 0, 0, 0, 0, 0, 0, 0] msg3_ok=106 msg3_nok=121 conres_timer_expired=4 late_dl_harqs=0 late_ul_harqs=0 pucch_tot_rb_usage_avg=4.89 pusch_rbs_per_tdd_slot_idx=[0, 0, 0, 0, 0, 0, 0, 16, 9, 3] pdsch_rbs_per_tdd_slot_idx=[9, 10, 10, 10, 9, 9, 1, 0, 0, 0] max_crc_delay=2.5ms max_ce_delay=2.5ms max_pucch_harq_delay=2ms max_pusch_harq_delay=2ms max_sr_to_pusch_delay=5ms avg_prach_delay=5 events=[{rnti=0x4601 slot=242.4 type=ue_create}, {rnti=0x4601 slot=258.18 type=ue_reconf}, ... (177 remaining events) ...]"
SCHED_UE_LINE = "2026-06-29T14:10:11.345650 [METRICS ] Scheduler UE ue=81 pci=1 rnti=0x4666 metrics: cqi=15 dl_ri=1.0 dl_mcs=13 dl_brate=8.78kbps dl_nof_ok=8 dl_nof_nok=0 dl_error_rate=0% dl_bs=0 dl_nof_prbs=72 dl_olla=0 pusch_snr_db=49.3 pusch_rsrp_db=-11.0 ul_ri=1 ul_mcs=22 ul_brate=12.9kbps ul_nof_ok=3 ul_nof_nok=0 ul_error_rate=0% ul_nof_prbs=36 bsr=0 sr_count=3 f0f1_invalid_harqs=0 f2f3f4_invalid_harqs=0 f2f3f4_invalid_csis=3 pusch_invalid_harqs=0 pusch_invalid_csis=0 ul_olla=0 ta=-8ns srs_ta=n/a last_phr=38 max_pdsch_distance=80ms max_pusch_distance=40ms avg_ul_ce_delay=2.33ms max_ul_ce_delay=2.5ms avg_crc_delay=2.17ms max_crc_delay=2.5ms avg_pusch_harq_delay=n/a max_pusch_harq_delay=n/a avg_pucch_harq_delay=2ms max_pucch_harq_delay=2ms avg_sr_to_pusch_delay=5ms max_sr_to_pusch_delay=5ms max_dl_lcid0_flush_delay=4.5ms max_dl_lcid1_flush_delay=1.5ms"
SCHED_UE_LINE_NA = "2026-06-29T14:10:11.345400 [METRICS ] Scheduler UE ue=34 pci=1 rnti=0x462d metrics: cqi=n/a dl_ri=n/a dl_mcs=0 dl_brate=0bps dl_nof_ok=0 dl_nof_nok=0 dl_error_rate=0% dl_bs=303 dl_nof_prbs=0 pusch_snr_db=n/a pusch_rsrp_db=n/a ul_ri=1 ul_mcs=0 ul_brate=0bps ul_nof_ok=0 ul_nof_nok=0 ul_error_rate=0% ul_nof_prbs=0 bsr=0 sr_count=0 f0f1_invalid_harqs=0 f2f3f4_invalid_harqs=0 f2f3f4_invalid_csis=15 pusch_invalid_harqs=0 pusch_invalid_csis=0 ta= 0s srs_ta=n/a last_phr=n/a max_pdsch_distance=0ms max_pusch_distance=0ms avg_ul_ce_delay=n/a max_ul_ce_delay=n/a avg_crc_delay=n/a max_crc_delay=n/a avg_pusch_harq_delay=n/a max_pusch_harq_delay=n/a avg_pucch_harq_delay=n/a max_pucch_harq_delay=n/a avg_sr_to_pusch_delay=n/a max_sr_to_pusch_delay=n/a"
# Synthetic.
RLC_LINE = "2026-06-29T14:10:11.346000 [METRICS ] RLC Metrics: du=0 ue=1 rb=DRB1 TX=[num_sdus=120 sdu_rate=1.2Mbps dropped_sdus=0 discarded_sdus=0 num_pdus_no_segm=118 pdu_rate_no_segm=1.1Mbps num_pdus_with_segm=2 pdu_rate_with_segm=12.0kbps num_retx=1 retx_rate=4.5kbps ctrl_pdus=3 ctrl_rate=240bps pull_latency_avg=12.5u pull_latency_sum=1.5ms num_ack_latency_meas=4 ack_latency_min=10ms ack_latency_avg=12.0ms ack_latency_max=15ms num_handle_status_latency_meas=0 t_poll_nof_expiration=0 pdu_latency_hist=[ 100 18 1.2k 0] max_pull_latency=35.20us] RX=[num_sdus=80 sdu_rate=640kbps num_pdus=82 pdu_rate=660kbps num_sdu_segments=2 sdu_segmments_rate=1.0kbps ctrl_pdus=3 ctrl_rate=240bps]"
PHY_LINE = "2026-08-06T15:06:59.964187 [METRICS ] PHY metrics: dl_processing_max_latency=81.6us dl_processing_max_slot=146.7 ul_processing_max_latency=133.9us ul_processing_max_slot=148.19 ldpc_encoder_avg_latency=3.6us ldpc_encoder_max_latency=5.6us ldpc_decoder_avg_latency=19.9us ldpc_decoder_max_latency=26.5us ldpc_decoder_avg_nof_iter=1.0"
OFH_TIMING_LINE = "2026-08-06T15:06:58.964118 [METRICS ] OFH timing metrics: nof_skipped_symbols=0 skipped_symbols_max_burst=0 symbol_notification_max_latency=6.97us symbol_notification_avg_latency=0.46us"
OFH_SECTOR_LINE = "2026-08-06T15:06:58.964128 [METRICS ] OFH sector#0 metrics: pci=1 received messages stats: rx_total=768 rx_early=0 rx_on_time=768 rx_late=0 earliest_msg_us=0.00 latest_msg_us=71.43, nof_missed_uplink_symbols=0 nof_missed_prach_occasions=12 ether_rx: cpu_usage=0.3% max_latency=1.06us avg_latency=1.40us throughput=5.55Mbps rx_bytes=284224; ether_tx: cpu_usage=1.0% max_latency=2.79us avg_latency=0.95us throughput=565.00Mbps tx_bytes=28956048; ecpri: nof_past_seqid_msg=0 nof_future_seqid_msg=0; rcv_prach: nof_dropped_msg=0 cpu_usage=0.2% max_latency=7.97us avg_latency=1.12us; rcv_ul: nof_dropped_msg=0 cpu_usage=0.0% max_latency=0.00us avg_latency=0.00us; tx_dl_up: cpu_usage=2.9% dl_up_max_latency=64.02us dl_up_avg_latency=42.40us; tx_dl_cp: cpu_usage=0.0% dl_cp_max_latency=2.07us dl_cp_avg_latency=0.59us; tx_ul_cp: cpu_usage=0.0% ul_cp_max_latency=2.44us ul_cp_avg_latency=0.36us; message_tx: cpu_usage=2.1% max_latency=13.18us avg_latency=1.12us; tx_kpis: nof_late_dl_rgs=1 nof_late_ul_req=0 nof_late_cp_dl=0 nof_late_up_dl=0 nof_late_cp_ul=0"
# Synthetic.
PDCP_LINE = "2026-08-06T15:06:59.000001 [METRICS ] PDCP Metrics: ue=1 rb=DRB1 tx=[num_sdus=100 sdu_rate=1.2Mbps dropped_sdus=0 num_pdus=100 pdu_rate=1.2Mbps num_discard_timeouts=0 avg_pdu_latency=15.20us pdu_latency_hist=[90 10 0 0] min_pdu_latency=3.10us max_pdu_latency=80.00us crypto_cpu_usage=0.50%] rx=[num_sdus=50 sdu_rate=400kbps num_dropped_pdus=0 num_pdus=50 pdu_rate=400kbps num_integrity_verified_pdus=0 num_integrity_unverified_pdus=50 num_integrity_failed_pdus=0 num_t_reordering_timeouts=0 avg_reordering_delay=0.00ms reordering_counter=0 avg_sdu_latency=12.00us sdu_latency_hist=[50 0 0 0] min_sdu_latency={na} max_sdu_latency={na} crypto_cpu_usage=0.20%]"
# Synthetic.
NRUP_LINE = "2026-08-06T15:06:59.000002 [METRICS ] NRUP Metrics: ue=1 drb=DRB1 tx=[num_sdus=10 sdu_rate=1.2Mbps num_dropped_sdus=0 num_sdu_discards=0 num_pdus=10] rx=[num_pdus=12 num_dropped_pdus=0 num_sdus=12 sdu_rate=900kbps num_dds=3 num_dds_failures=0]"
# Synthetic.
E1AP_LINE = "2026-08-06T15:06:59.000003 [METRICS ] CU-UP E1AP metrics: num_success_ctx_setup=2 num_success_ctx_modification=1 num_ctx_releases=1 release_latency_avg=1.5m release_latency_hist=[ 1 0 0] max_release_latency=1500µs"
EXEC_LINE = '2026-08-06T15:06:59.684258 [METRICS ] Executor metrics "cu_cp_exec": nof_executes=40 nof_defers=1 enqueue_avg=7usec enqueue_max=48usec task_avg=77usec task_max=442usec cpu_load=0.1% nof_vol_ctxt_switch=2 nof_invol_ctxt_switch=0'
# Synthetic.
RESOURCE_USAGE_LINE = "2026-08-06T15:06:59.000004 [METRICS ] App resource usage: cpu_usage=12.50%, mem_total=812.25 MB, mem_usage=3.10%, power_consumption=45.00 Watts"
# Synthetic.
BUFFER_POOL_LINE = "2026-08-06T15:06:59.000005 [METRICS ] Buffer pool: central_cache_size=2048 segments"


class MetricsParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = metrics.MetricsParser()

    def test_du_manager(self):
        rec = self.parser.parse(DU_MANAGER_LINE)
        self.assertEqual(rec["layer"], "du_manager")
        self.assertEqual(rec["nof_ue_creations"], 106)
        self.assertEqual(rec["max_ue_creation_latency"], 82651)
        self.assertEqual(self.parser.units["du_manager"]["max_ue_creation_latency"], "us")

    def test_mac(self):
        rec = self.parser.parse(MAC_LINE)
        self.assertEqual(rec["timestamp"], datetime.fromisoformat("2026-06-29T14:10:06.324561"))
        self.assertEqual(rec["layer"], "mac")
        self.assertEqual(rec["pci"], 1)
        self.assertEqual(rec["slots_start"], "853.19")
        self.assertEqual(rec["slots_end"], "864.0")
        self.assertEqual(rec["slots_hfn_wraps"], 0)
        self.assertEqual(rec["slot_duration"], 500)
        self.assertEqual(rec["wall_clock_latency_max"], 88)
        self.assertEqual(rec["slot_ind_msg_time_diff_max_slot"], "855.9")
        self.assertEqual(self.parser.units["mac"]["wall_clock_latency_avg"], "us")

    def test_mac_slot_range_with_hfn_wrap(self):
        rec = self.parser.parse(MAC_LINE_HFN)
        self.assertEqual(rec["slots_start"], "964.0")
        self.assertEqual(rec["slots_end"], "40.0")
        self.assertEqual(rec["slots_hfn_wraps"], 1)
        self.assertEqual(rec["ul_tti_req_latency_max_slot"], "1007.19")

    def test_sched_cell(self):
        rec = self.parser.parse(SCHED_LINE)
        self.assertEqual(rec["layer"], "sched")
        self.assertEqual(rec["pci"], 1)
        self.assertEqual(rec["total_dl_brate"], 996_000)
        self.assertEqual(rec["total_ul_brate"], 2_600_000.0)
        self.assertEqual(rec["pdschs_per_slot"], 1.08)
        self.assertEqual(rec["max_latency_slot"], "332.4")
        self.assertEqual(rec["latency_hist"], [1864, 132, 4, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(rec["pdsch_rbs_per_tdd_slot_idx"], [9, 10, 10, 10, 9, 9, 1, 0, 0, 0])
        self.assertEqual(rec["max_crc_delay"], 2500.0)
        self.assertEqual(rec["max_pucch_harq_delay"], 2000)
        self.assertEqual(rec["avg_prach_delay"], 5)
        self.assertEqual(rec["events"], [
            {"rnti": "0x4601", "slot": "242.4", "type": "ue_create"},
            {"rnti": "0x4601", "slot": "258.18", "type": "ue_reconf"},
        ])
        self.assertEqual(rec["events_remaining"], 177)
        units = self.parser.units["sched"]
        self.assertEqual(units["avg_prach_delay"], "slots")
        self.assertEqual(units["max_crc_delay"], "us")
        self.assertEqual(units["total_dl_brate"], "bps")
        self.assertNotIn("nof_ues", units)

    def test_sched_ue(self):
        rec = self.parser.parse(SCHED_UE_LINE)
        self.assertEqual(rec["layer"], "sched_ue")
        self.assertEqual((rec["ue"], rec["pci"], rec["rnti"]), (81, 1, "0x4666"))
        self.assertEqual(rec["dl_brate"], 8780.0)
        self.assertEqual(rec["dl_error_rate"], 0)
        self.assertEqual(rec["pusch_rsrp_db"], -11.0)
        self.assertEqual(rec["ta"], -0.008)
        self.assertIsNone(rec["srs_ta"])
        self.assertIsNone(rec["avg_pusch_harq_delay"])
        self.assertEqual(rec["avg_ul_ce_delay"], 2330.0)
        units = self.parser.units["sched_ue"]
        self.assertEqual(units["ta"], "us")
        self.assertEqual(units["dl_error_rate"], "%")
        self.assertEqual((units["pusch_snr_db"], units["pusch_rsrp_db"], units["last_phr"]), ("dB", "dBFS", "dB"))
        self.assertEqual((units["dl_bs"], units["bsr"], units["dl_olla"]), ("bytes", "bytes", "dB"))

    def test_sched_ue_si_prefixed_bytes(self):
        rec = self.parser.parse(SCHED_UE_LINE.replace("dl_bs=0", "dl_bs=5.74k"))
        self.assertEqual(rec["dl_bs"], 5740.0)
        self.assertEqual(self.parser.units["sched_ue"]["dl_bs"], "bytes")

    def test_sched_ue_unavailable_values(self):
        rec = self.parser.parse(SCHED_UE_LINE_NA)
        self.assertIsNone(rec["cqi"])
        self.assertIsNone(rec["pusch_snr_db"])
        self.assertIsNone(rec["last_phr"])
        self.assertEqual(rec["ta"], 0)
        self.assertEqual(rec["dl_bs"], 303)

    def test_sched_ue_rsrp_overload(self):
        line = SCHED_UE_LINE.replace("pusch_rsrp_db=-11.0", "pusch_rsrp_db=ovl")
        self.assertIsNone(self.parser.parse(line)["pusch_rsrp_db"])

    def test_rlc(self):
        rec = self.parser.parse(RLC_LINE)
        self.assertEqual(rec["layer"], "rlc")
        self.assertEqual((rec["du"], rec["ue"], rec["rb"]), (0, 1, "DRB1"))
        self.assertEqual(rec["tx_sdu_rate"], 1_200_000.0)
        self.assertEqual(rec["tx_pull_latency_avg"], 12.5)
        self.assertEqual(rec["tx_pull_latency_sum"], 1500.0)
        self.assertEqual(rec["tx_ack_latency_avg"], 12000.0)
        self.assertEqual(rec["tx_pdu_latency_hist"], [100, 18, 1200.0, 0])
        self.assertEqual(rec["tx_max_pull_latency"], 35.2)
        self.assertEqual(rec["rx_sdu_segmments_rate"], 1000.0)
        self.assertEqual(self.parser.units["rlc"]["tx_ack_latency_min"], "us")
        self.assertEqual(self.parser.units["rlc"]["tx_pull_latency_avg"], "us")

    def test_rlc_std_optional_values(self):
        line = RLC_LINE.replace("t_poll_nof_expiration=0", "t_poll_nof_expiration=2 t_poll_latency_avg=5.5us t_poll_latency_min=optional(3)us t_poll_latency_max=optional(9)us")
        rec = self.parser.parse(line)
        self.assertEqual((rec["tx_t_poll_latency_min"], rec["tx_t_poll_latency_max"]), (3, 9))
        self.assertEqual(self.parser.units["rlc"]["tx_t_poll_latency_min"], "us")

    def test_phy(self):
        rec = self.parser.parse(PHY_LINE)
        self.assertEqual(rec["layer"], "phy")
        self.assertEqual(rec["ul_processing_max_latency"], 133.9)
        self.assertEqual(rec["ul_processing_max_slot"], "148.19")
        self.assertEqual(rec["ldpc_decoder_avg_nof_iter"], 1.0)

    def test_phy_verbose_continuation_lines_are_ignored(self):
        self.assertIsNone(self.parser.parse("  DL processing:          max_latency=81.60 us in slot=146.7"))

    def test_ofh_timing(self):
        rec = self.parser.parse(OFH_TIMING_LINE)
        self.assertEqual(rec["layer"], "ofh_timing")
        self.assertEqual(rec["symbol_notification_max_latency"], 6.97)

    def test_ofh_sector(self):
        rec = self.parser.parse(OFH_SECTOR_LINE)
        self.assertEqual(rec["layer"], "ofh_sector")
        self.assertEqual((rec["sector"], rec["pci"]), (0, 1))
        self.assertEqual(rec["rx_total"], 768)
        self.assertEqual(rec["latest_msg_us"], 71.43)
        self.assertEqual(rec["nof_missed_prach_occasions"], 12)
        self.assertEqual(rec["ether_rx_cpu_usage"], 0.3)
        self.assertEqual(rec["ether_tx_throughput"], 565_000_000.0)
        self.assertEqual(rec["ecpri_nof_past_seqid_msg"], 0)
        self.assertEqual(rec["tx_dl_up_dl_up_max_latency"], 64.02)
        self.assertEqual(rec["tx_kpis_nof_late_dl_rgs"], 1)
        units = self.parser.units["ofh_sector"]
        self.assertEqual(units["ether_rx_cpu_usage"], "%")
        self.assertEqual((units["latest_msg_us"], units["ether_tx_tx_bytes"]), ("us", "bytes"))

    def test_pdcp(self):
        rec = self.parser.parse(PDCP_LINE)
        self.assertEqual(rec["layer"], "pdcp")
        self.assertEqual((rec["ue"], rec["rb"]), (1, "DRB1"))
        self.assertEqual(rec["tx_sdu_rate"], 1_200_000.0)
        self.assertEqual(rec["tx_pdu_latency_hist"], [90, 10, 0, 0])
        self.assertEqual(rec["tx_crypto_cpu_usage"], 0.5)
        self.assertIsNone(rec["rx_min_sdu_latency"])
        self.assertEqual(rec["rx_avg_reordering_delay"], 0.0)

    def test_nrup(self):
        rec = self.parser.parse(NRUP_LINE)
        self.assertEqual(rec["layer"], "nrup")
        self.assertEqual((rec["ue"], rec["drb"]), (1, "DRB1"))
        self.assertEqual(rec["rx_sdu_rate"], 900_000)
        self.assertEqual(rec["rx_num_dds"], 3)

    def test_e1ap(self):
        rec = self.parser.parse(E1AP_LINE)
        self.assertEqual(rec["layer"], "e1ap")
        self.assertEqual(rec["num_success_ctx_setup"], 2)
        self.assertEqual(rec["release_latency_avg"], 1500.0)
        self.assertEqual(rec["release_latency_hist"], [1, 0, 0])
        self.assertEqual(rec["max_release_latency"], 1500)
        self.assertEqual(self.parser.units["e1ap"]["max_release_latency"], "us")
        self.assertEqual(self.parser.units["e1ap"]["release_latency_avg"], "us")

    def test_e1ap_without_releases(self):
        line = E1AP_LINE.replace("release_latency_avg=1.5m", "release_latency_avg=NaN")
        self.assertIsNone(self.parser.parse(line)["release_latency_avg"])

    def test_executor(self):
        rec = self.parser.parse(EXEC_LINE)
        self.assertEqual(rec["layer"], "exec")
        self.assertEqual(rec["executor"], "cu_cp_exec")
        self.assertEqual(rec["task_max"], 442)
        self.assertEqual(rec["cpu_load"], 0.1)
        self.assertEqual(rec["nof_invol_ctxt_switch"], 0)

    def test_resource_usage(self):
        rec = self.parser.parse(RESOURCE_USAGE_LINE)
        self.assertEqual(rec["layer"], "resource_usage")
        self.assertEqual(rec["cpu_usage"], 12.5)
        self.assertEqual(rec["mem_total"], 812.25)
        self.assertEqual(rec["power_consumption"], 45.0)
        units = self.parser.units["resource_usage"]
        self.assertEqual((units["mem_total"], units["power_consumption"]), ("MB", "W"))

    def test_buffer_pool(self):
        rec = self.parser.parse(BUFFER_POOL_LINE)
        self.assertEqual(rec["layer"], "buffer_pool")
        self.assertEqual(rec["central_cache_size"], 2048)
        self.assertEqual(self.parser.units["buffer_pool"]["central_cache_size"], "segments")

    def test_layer_selection(self):
        parser = metrics.MetricsParser(["mac"])
        self.assertIsNone(parser.parse(SCHED_LINE))
        self.assertIsNotNone(parser.parse(MAC_LINE))

    def test_unknown_layer_raises(self):
        with self.assertRaises(ValueError):
            metrics.MetricsParser(["upper_phy"])

    def test_non_metrics_logger_returns_none(self):
        self.assertIsNone(self.parser.parse("2026-06-29T14:10:11.345195 [SCHED   ] [I] Scheduler cell pci=1 metrics: nof_ues=1"))

    def test_unknown_metrics_line_returns_none(self):
        self.assertIsNone(self.parser.parse("2026-06-29T14:10:11.345195 [METRICS ] Foo metrics: a=1"))

    def test_status_lines_on_metrics_logger_return_none(self):
        self.assertIsNone(self.parser.parse("2026-06-29T14:10:11.345195 [METRICS ] [I] Started the executor metrics backend worker"))

    def test_malformed_line_keeps_context(self):
        rec = self.parser.parse("2026-06-29T14:10:11.345195 [METRICS ] Scheduler cell pci=2 metrics: garbage")
        self.assertEqual(rec["pci"], 2)
        self.assertEqual(rec["layer"], "sched")

    def test_unit_conflict_warns_once_and_keeps_first_unit(self):
        prefix = "2026-06-29T14:10:11.345195 [METRICS ] Scheduler cell pci=1 metrics: "
        self.parser.parse(prefix + "foo=1ms")
        with self.assertLogs("parsers", "WARNING") as logs:
            self.parser.parse(prefix + "foo=1%")
            self.parser.parse(prefix + "foo=2%")
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(self.parser.units["sched"]["foo"], "us")

    def test_unknown_unit_warns_and_passes_through(self):
        line = "2026-06-29T14:10:11.345195 [METRICS ] Scheduler cell pci=1 metrics: foo=3dB"
        with self.assertLogs("parsers", "WARNING"):
            rec = self.parser.parse(line)
        self.assertEqual(rec["foo"], 3)
        self.assertNotIn("foo", self.parser.units["sched"])


class ExtractMetricFieldsTest(unittest.TestCase):
    def test_time_units_to_us(self):
        fields = metrics.extract_metric_fields("a=3ms b=2.5ms c=148ns d=1.2us e=500usec f=-8ns g=1s h=2.22e+03ms i=5ps")
        self.assertEqual(fields, {"a": 3000, "b": 2500.0, "c": 0.148, "d": 1.2, "e": 500, "f": -0.008, "g": 1_000_000, "h": 2_220_000.0, "i": 5e-6})
        self.assertIsInstance(fields["a"], int)
        self.assertIsInstance(fields["b"], float)

    def test_bitrates_to_bps(self):
        fields = metrics.extract_metric_fields("a=996kbps b=2.60Mbps c=1.4Gbps d=0bps")
        self.assertEqual(fields, {"a": 996_000, "b": 2_600_000.0, "c": 1_400_000_000.0, "d": 0})

    def test_bare_si_prefix(self):
        self.assertEqual(metrics.extract_metric_fields("dl_bs=5.74k bsr=3M x=303"), {"dl_bs": 5740.0, "bsr": 3_000_000, "x": 303})

    def test_scientific_notation_without_unit(self):
        self.assertEqual(metrics.extract_metric_fields("dl_olla=1e-05"), {"dl_olla": 1e-05})

    def test_unavailable_values(self):
        fields = metrics.extract_metric_fields("a=n/a b={na} c=NaN d=ovl e=n/a")
        self.assertEqual(fields, dict.fromkeys("abcde"))

    def test_space_after_equals(self):
        self.assertEqual(metrics.extract_metric_fields("ta= 0s dl_brate= 12kbps"), {"ta": 0, "dl_brate": 12000})

    def test_hex_and_word_values(self):
        self.assertEqual(metrics.extract_metric_fields("rnti=0x4601 type=ue_create connected=true"), {"rnti": "0x4601", "type": "ue_create", "connected": "true"})

    def test_spaced_units(self):
        fields = metrics.extract_metric_fields("cpu_usage=1.50%, mem_total=2.00 MB, power_consumption=3.10 Watts")
        self.assertEqual(fields, {"cpu_usage": 1.5, "mem_total": 2.0, "power_consumption": 3.1})

    def test_nested_key_value_lists(self):
        fields = metrics.extract_metric_fields("TX=[num_sdus=3 sdu_rate=1.2kbps] RX=[num_pdus=4]")
        self.assertEqual(fields, {"tx_num_sdus": 3, "tx_sdu_rate": 1200.0, "rx_num_pdus": 4})

    def test_number_lists(self):
        fields = metrics.extract_metric_fields("a=[5] b=[] c=[ 1.2k 3 n/a] d=[1, 2]")
        self.assertEqual(fields, {"a": [5], "b": [], "c": [1200.0, 3, None], "d": [1, 2]})

    def test_record_lists(self):
        text = "events=[{rnti=0x4601 slot=242.4 type=ue_create}, {rnti=0x4607 slot=247.10 type=ue_reconf}, ... (177 remaining events) ...] x=1"
        fields = metrics.extract_metric_fields(text)
        self.assertEqual(fields["events"], [
            {"rnti": "0x4601", "slot": "242.4", "type": "ue_create"},
            {"rnti": "0x4607", "slot": "247.10", "type": "ue_reconf"},
        ])
        self.assertEqual(fields["events_remaining"], 177)
        self.assertEqual(fields["x"], 1)

    def test_sections(self):
        fields = metrics.extract_metric_fields("a=1, b=2 ether_rx: cpu_usage=0.3% x=1; ecpri: y=2 rcv_ul: z=3; w=4")
        self.assertEqual(fields, {"a": 1, "b": 2, "ether_rx_cpu_usage": 0.3, "ether_rx_x": 1, "ecpri_y": 2, "rcv_ul_z": 3, "w": 4})


@unittest.skipUnless(importlib.util.find_spec("pandas"), "pandas not installed")
class ToDataFrameTest(unittest.TestCase):
    def test_one_row_per_layer_record(self):
        df = metrics.to_dataframe([MAC_LINE, SCHED_LINE, MAC_LINE_HFN], "mac")
        self.assertEqual(len(df), 2)
        self.assertEqual(list(df["wall_clock_latency_max"]), [88, 63])
        self.assertEqual(df.attrs["units"]["wall_clock_latency_max"], "us")


class ParseSlotTest(unittest.TestCase):
    def test_parse_slot(self):
        self.assertEqual(metrics.parse_slot("40.10"), (40, 10))


if __name__ == "__main__":
    unittest.main()
