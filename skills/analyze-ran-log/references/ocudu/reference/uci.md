# UCI outcomes

What the gNB records as the result of decoding a UE's **Uplink Control Information
(UCI)**, and how each outcome reads in `gnb.log` / `metrics.json`. UCI carries
**HARQ-ACK**, **SR** (scheduling request; LRR is treated the same), and **CSI**
(TS 38.213 §9.2, TS 38.300 §5.3.3), on PUCCH (Formats 0/1 for ≤2 bits, 2/3/4 for
larger payloads) or multiplexed on PUSCH.

Every outcome is a **receiver verdict**: the gNB has to decide what the UE sent
even when it may have transmitted nothing.

## HARQ-ACK: ACK / NACK / DTX

| Outcome | Meaning | Typical cause |
|---|---|---|
| **ACK**  | UE decoded the PDSCH TB. | good link |
| **NACK** | UE got the grant but failed to decode the TB. | MCS too high / interference |
| **DTX**  | gNB expected feedback but detected no valid UCI. | UE missed the PDCCH (never sent feedback), or the PUCCH/PUSCH itself was undecodable |

DTX is **inferred by the gNB, never sent by the UE** — the UE only ever sends ACK
or NACK. A DTX is scored as a NACK for retransmission, so a **DL KO can be a real
NACK *or* an undetected ACK** — different root causes. Telling them apart, and the
full DL/UL KO (BLER) diagnostic, lives in
[`harq-ko-bler.md`](../troubleshooting/harq-ko-bler.md); this file is just the
vocabulary.

Why the split matters: only a **NACK** feeds outer-loop link adaptation (lowers
MCS); a **DTX** is excluded from OLLA (the UE likely never saw the grant, so it
says nothing about the PDSCH MCS). Both cause a DL retransmission (RV cycling
`0→2→3→1…`) and, if never resolved, a `harq_ack_timeout` event. Rule of thumb:
**NACK-heavy** → PDSCH MCS / coverage; **DTX-heavy** → PDCCH reachability (UE not
decoding the DL assignment) or UL control-channel coverage.

## PHY / FAPI detection-status vocabulary

The status the PHY reports for a CRC-protected UCI payload (HARQ or CSI on PUSCH
or PUCCH F2/3/4) — enum `uci_pusch_or_pucch_f2_3_4_detection_status`:

| Status | Payload | Collapses to |
|---|---|---|
| `crc_pass` | valid | ACK/NACK per bits, or valid CSI |
| `crc_failure` | corrupt | DTX / invalid (dropped) |
| `dtx` | nothing detected | DTX |
| `no_dtx` | valid (short, CRC-less) | ACK/NACK, or valid CSI |
| `dtx_not_checked` | unknown | DTX / invalid (dropped) |

Only `crc_pass` and `no_dtx` yield a usable payload; everything else is dropped
and bumps the `*_invalid_harqs` / `*_invalid_csis` counters (below). Short PUCCH
Format 0/1 HARQ has no CRC and reports `ack` / `nack` / `dtx` directly.

## SR: positive / negative

SR is binary — **positive** (UE wants an UL grant → the scheduler allocates a
PUSCH opportunity) or **negative** (nothing to send). When SR shares a PUCCH with
HARQ/CSI, an **all-zero** SR field is a negative SR across all configured SR
resources (TS 38.213 §9.2.5.1). An SR that never converts to a grant shows up as a
large `max_sr_to_pusch_delay` (the UL-scheduler bottleneck discussed in
`../troubleshooting/harq-ko-bler.md` § Release-phase KOs).

## CSI: valid / invalid

A CSI report is either decoded (**valid**) or not. Only valid CSI updates
link-adaptation (CQI/RI/PMI); invalid CSI is discarded, with no MCS update. On
PUSCH / PUCCH F2-4 the validity comes from the same detection status, and **Part 2's
size is derived from Part 1** (TS 38.214 §5.2.3) — if Part 1 is not decoded, Part 2
is unusable. Undecoded reports are counted by `nof_pucch_f2f3f4_invalid_csis` /
`nof_pusch_invalid_csis`.

## Where the outcomes appear

**Per-UE metrics** (`stdout.log` table; `[METRICS] Scheduler UE` lines;
`metrics.json` `ue_list[]`):
- `ok` / `nok` / `(%)` — successful TBs / KOs / BLER, DL and UL separately. DL
  `nok` (`dl_nof_nok`) lumps real NACKs together with DTX-scored-as-NACK; UL `nok`
  (`ul_nof_nok`) is a direct PUSCH `crc=KO`, with no DTX ambiguity.
- `cqi` / `ri` — from the last **valid** CSI (blank / `n/a` before the first one).

**Cell metrics** (`metrics.json`; `[METRICS] Scheduler cell`):
- `nof_pucch_f0f1_invalid_harqs`, `nof_pucch_f2f3f4_invalid_harqs`,
  `nof_pusch_invalid_harqs` — HARQ reports dropped as DTX / CRC-fail. High values
  ⇒ UL control reception problem, and the way to tell an undetected-ACK DL KO from
  a real NACK.
- `nof_pucch_f2f3f4_invalid_csis`, `nof_pusch_invalid_csis` — undecoded CSI.
- `failed_uci` / `nof_failed_uci_allocs` — the scheduler could **not place** the
  PUCCH/PUSCH for a PDSCH's HARQ-ACK, so the DL grant is *skipped* entirely (not
  left unacked) → lower throughput, **not** a KO. See
  `../troubleshooting/harq-ko-bler.md` § Common misattributions.
- `late_dl_harqs` / `late_ul_harqs`, and the `harq_ack_timeout` scheduler event —
  HARQ feedback arrived too late / never.

**PHY per-slot lines**: PUCCH lines carry the UCI `metric` / `sinr` and the decoded
HARQ codes (incl. DTX); PUSCH lines carry `crc=OK`/`crc=KO`. A releasing UE with
PUCCH `metric≈0`, deeply negative `sinr`, and DTX HARQ codes is the classic
missing-UL-feedback signal (`../troubleshooting/harq-ko-bler.md` § Release-phase KOs).

## Vocabulary → source

The outcome enums — `mac_harq_ack_report_status {nack, ack, dtx}`,
`uci_pucch_f0_or_f1_harq_values {nack, ack, dtx}`, and
`uci_pusch_or_pucch_f2_3_4_detection_status` — are defined in the OCUDU tree under
`include/ocudu/ran/harq_id.h` and `include/ocudu/ran/uci/uci_mapping.h`, for
correlating a log field back to code.

### Spec references
- UCI content / PUCCH reporting — TS 38.213 §9.2; TS 38.300 §5.3.3.
- Negative-SR encoding — TS 38.213 §9.2.5.1.
- CSI Part 1 / Part 2 on PUSCH — TS 38.214 §5.2.3.
- ACK missed-detection (DTX) receiver requirements — TS 38.104 §8.3, §11.3.
