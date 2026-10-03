# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import importlib.util
import unittest
from datetime import datetime

from parsers.log import metrics

SCHED_LINE = "2025-04-04T15:55:29.878489 [METRICS ] Scheduler cell pci=1 metrics: total_dl_brate=1.4Gbps total_ul_brate=99Mbps nof_prbs=273 nof_dl_slots=1600 nof_ul_slots=400 error_indications=0 pdsch_rbs_per_slot=271 pusch_rbs_per_slot=251 pdschs_per_slot=3 puschs_per_slot=2 failed_pdcch=0 failed_uci=30 nof_ues=32 mean_latency=58usec max_latency=492usec max_latency_slot=814.16 latency_hist=[742, 1098, 150, 3, 3, 2, 1, 0, 0, 1] max_crc_delay=3ms max_ce_delay=4ms max_pucch_harq_delay=2.5ms max_pusch_harq_delay=2.5ms"
MAC_LINE = "2025-04-04T15:37:27.599168 [METRICS ] MAC cell pci=1 metrics: nof_slots=2000 slot_duration=500usec nof_voluntary_context_switches=1 nof_involuntary_context_switches=261 wall_clock_latency=[avg=127usec max=533usec max_slot=132.16] dl_tti_req_latency=[avg=67usec max=337usec max_slot=108.16] tx_data_req_latency=[avg=51usec max=268usec max_slot=132.16] slot_ind_latency=[avg=7usec max=41usec max_slot=132.17]"
MAC_LINE_SLOTS = "2025-11-07T09:35:25.129220 [METRICS ] MAC cell pci=1 metrics: slots=[100.0, 200.0) nof_slots=2000 slot_duration=500usec nof_voluntary_context_switches=0 nof_involuntary_context_switches=209 wall_clock_latency=[avg=25usec max=274usec max_slot=171.6] sched_latency=[avg=13usec max=131usec max_slot=101.15] dl_tti_req_latency=[avg=12usec max=258usec max_slot=171.6] tx_data_req_latency=[avg=7usec max=24usec max_slot=104.3] ul_tti_req_latency=[avg=9usec max=125usec max_slot=198.19] slot_ind_dequeue_latency=[avg=28usec max=102usec max_slot=167.14] slot_ind_msg_time_diff=[avg=541usec max=2374usec max_slot=125.4]\n"
MAC_LINE_HFN = "2025-11-07T09:38:18.654757 [METRICS ] MAC cell pci=1 metrics: slots=[984.0, 60.0(+1 HFNs)) nof_slots=2000 slot_duration=500usec nof_voluntary_context_switches=0 nof_involuntary_context_switches=37793 wall_clock_latency=[avg=521usec max=61871usec max_slot=1021.13] sched_latency=[avg=459usec max=61851usec max_slot=1021.13] dl_tti_req_latency=[avg=55usec max=2033usec max_slot=985.12] tx_data_req_latency=[avg=10usec max=296usec max_slot=40.10] ul_tti_req_latency=[avg=52usec max=584usec max_slot=1020.18] slot_ind_dequeue_latency=[avg=58usec max=10865usec max_slot=1022.9] slot_ind_msg_time_diff=[avg=2385usec max=146932usec max_slot=6.5]"
UPPER_PHY_LINE = "2025-07-10T05:10:51.686748 [METRICS ] Upper PHY sector#0 metrics: PHY metrics: dl_processing_max_latency=569.3us dl_processing_max_slot=203.0 ul_processing_max_latency=1077.7us ul_processing_max_slot=160.19 ldpc_encoder_avg_latency=2.6us ldpc_encoder_max_latency=13.7us ldpc_decoder_avg_latency=53.4us ldpc_decoder_max_latency=384.5us ldpc_decoder_avg_nof_iter=1.6"
EXEC_LINE = '2025-04-23T13:52:12.765052 [METRICS ] [I] Executor metrics "slot_ind_exec#0": nof_executes=2001 nof_defers=0 enqueue_avg=6usec enqueue_max=615usec task_avg=35usec task_max=314usec nof_vol_ctxt_switch=31 nof_invol_ctxt_switch=16'
OFH_LINE = "2025-08-25T23:14:30.687135 [METRICS ] OFH metrics: timing metrics: nof_skipped_symbols=0 skipped_symbols_max_burst=0; sector#0 pci=1 received messages stats: rx_total=6800 rx_early=0 rx_on_time=6800 rx_late=0 earliest_msg_us=35.71 latest_msg_us=321.43, nof_missed_uplink_symbols=0 nof_missed_prach_occasions=0; ether_rx: cpu_usage=0.7% max_latency=2.62us avg_latency=0.48us throughput=695.75Mbps rx_bytes=86881600; ether_tx: cpu_usage=10.1% max_latency=6.25us avg_latency=1.09us throughput=5217.27Mbps tx_bytes=651506320; ecpri: nof_past_seqid_msg=0 nof_future_seqid_msg=0; rcv_prach: nof_dropped_msg=0 cpu_usage=0.2% max_latency=6.25us avg_latency=1.78us; rcv_ul: nof_dropped_msg=0 cpu_usage=3.5% max_latency=26.62us avg_latency=6.30us; tx_dl_up: cpu_usage=28.5% dl_up_max_latency=121.63us dl_up_avg_latency=44.43us; tx_dl_cp: cpu_usage=0.6% dl_cp_max_latency=10.50us dl_cp_avg_latency=0.90us; tx_ul_cp: cpu_usage=0.1% ul_cp_max_latency=4.09us ul_cp_avg_latency=0.84us; message_tx: cpu_usage=14.7% max_latency=27.52us avg_latency=5.23us; tx_kpis: nof_late_dl_rgs=0 nof_late_ul_req=0 nof_late_cp_dl=0 nof_late_up_dl=0 nof_late_cp_ul=0"


class MetricsParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = metrics.MetricsParser()

    def test_sched_cell(self):
        rec = self.parser.parse(SCHED_LINE)
        self.assertEqual(rec["timestamp"], datetime.fromisoformat("2025-04-04T15:55:29.878489"))
        self.assertEqual(rec["layer"], "sched")
        self.assertEqual(rec["pci"], 1)
        self.assertEqual(rec["nof_ues"], 32)
        self.assertEqual(rec["total_dl_brate"], 1_400_000_000.0)
        self.assertEqual(rec["total_ul_brate"], 99_000_000)
        self.assertEqual(rec["max_crc_delay"], 3000)
        self.assertEqual(rec["max_pucch_harq_delay"], 2500.0)
        self.assertEqual(rec["max_latency_slot"], "814.16")
        self.assertEqual(rec["latency_hist"], [742, 1098, 150, 3, 3, 2, 1, 0, 0, 1])
        units = self.parser.units["sched"]
        self.assertEqual(units["max_crc_delay"], "us")
        self.assertEqual(units["mean_latency"], "us")
        self.assertEqual(units["total_dl_brate"], "bps")
        self.assertNotIn("nof_ues", units)

    def test_mac(self):
        rec = self.parser.parse(MAC_LINE)
        self.assertEqual(rec["layer"], "mac")
        self.assertEqual(rec["pci"], 1)
        self.assertEqual(rec["slot_duration"], 500)
        self.assertEqual(rec["wall_clock_latency_avg"], 127)
        self.assertEqual(rec["dl_tti_req_latency_max"], 337)
        self.assertEqual(rec["wall_clock_latency_max_slot"], "132.16")
        self.assertEqual(self.parser.units["mac"]["wall_clock_latency_avg"], "us")

    def test_mac_slot_range(self):
        rec = self.parser.parse(MAC_LINE_SLOTS)
        self.assertEqual(rec["slots_start"], "100.0")
        self.assertEqual(rec["slots_end"], "200.0")
        self.assertEqual(rec["slots_hfn_wraps"], 0)
        self.assertEqual(rec["wall_clock_latency_max"], 274)
        self.assertEqual(rec["tx_data_req_latency_max_slot"], "104.3")

    def test_mac_slot_range_with_hfn_wrap(self):
        rec = self.parser.parse(MAC_LINE_HFN)
        self.assertEqual(rec["slots_start"], "984.0")
        self.assertEqual(rec["slots_end"], "60.0")
        self.assertEqual(rec["slots_hfn_wraps"], 1)
        self.assertEqual(rec["nof_slots"], 2000)
        self.assertEqual(rec["tx_data_req_latency_max_slot"], "40.10")

    def test_upper_phy(self):
        rec = self.parser.parse(UPPER_PHY_LINE)
        self.assertEqual(rec["layer"], "upper_phy")
        self.assertEqual(rec["sector"], 0)
        self.assertEqual(rec["ul_processing_max_latency"], 1077.7)
        self.assertEqual(rec["ul_processing_max_slot"], "160.19")

    def test_executor(self):
        rec = self.parser.parse(EXEC_LINE)
        self.assertEqual(rec["layer"], "exec")
        self.assertEqual(rec["executor"], "slot_ind_exec#0")
        self.assertEqual(rec["task_max"], 314)

    def test_ofh_sections(self):
        rec = self.parser.parse(OFH_LINE)
        self.assertEqual(rec["nof_skipped_symbols"], 0)
        self.assertEqual(rec["ether_rx_max_latency"], 2.62)
        self.assertEqual(rec["ether_rx_cpu_usage"], 0.7)
        self.assertEqual(rec["ether_tx_throughput"], 5_217_270_000.0)
        self.assertEqual(self.parser.units["ofh"]["ether_rx_cpu_usage"], "%")

    def test_layer_selection(self):
        parser = metrics.MetricsParser(["mac"])
        self.assertIsNone(parser.parse(SCHED_LINE))
        self.assertIsNotNone(parser.parse(MAC_LINE))

    def test_unknown_layer_raises(self):
        with self.assertRaises(ValueError):
            metrics.MetricsParser(["foo"])

    def test_non_metrics_logger_returns_none(self):
        self.assertIsNone(self.parser.parse("2025-04-04T15:55:29.878489 [SCHED   ] [I] Scheduler cell pci=1 metrics: nof_ues=1"))

    def test_unknown_metrics_line_returns_none(self):
        self.assertIsNone(self.parser.parse("2025-04-04T15:55:29.878489 [METRICS ] Foo metrics: a=1"))

    def test_malformed_line_keeps_context(self):
        rec = self.parser.parse("2025-04-04T15:55:29.878489 [METRICS ] Scheduler cell pci=2 metrics: garbage")
        self.assertEqual(rec["pci"], 2)
        self.assertEqual(rec["layer"], "sched")

    def test_unit_conflict_warns_once_and_keeps_first_unit(self):
        prefix = "2025-04-04T15:55:29.878489 [METRICS ] Scheduler cell pci=1 metrics: "
        self.parser.parse(prefix + "foo=1ms")
        with self.assertLogs("parsers", "WARNING") as logs:
            self.parser.parse(prefix + "foo=1%")
            self.parser.parse(prefix + "foo=2%")
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(self.parser.units["sched"]["foo"], "us")

    def test_unknown_unit_warns_and_passes_through(self):
        line = "2025-04-04T15:55:29.878489 [METRICS ] Scheduler cell pci=1 metrics: foo=3dB"
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
        df = metrics.to_dataframe([MAC_LINE, SCHED_LINE, MAC_LINE_SLOTS], "mac")
        self.assertEqual(len(df), 2)
        self.assertEqual(list(df["wall_clock_latency_max"]), [533, 274])
        self.assertEqual(df.attrs["units"]["wall_clock_latency_max"], "us")


class ParseSlotTest(unittest.TestCase):
    def test_parse_slot(self):
        self.assertEqual(metrics.parse_slot("40.10"), (40, 10))


if __name__ == "__main__":
    unittest.main()
