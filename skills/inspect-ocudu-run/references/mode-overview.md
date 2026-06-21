# Overview mode

Produce one consolidated, factual overview of the whole run by delegating each
artifact to its `ran-log-reference` type and adding the cross-source (`correlate`)
layer on top. Do not enter the investigation loop. Ask `AskUserQuestion` only at
the end (escalation). Load `ran-log-reference` once via the `Skill` tool;
`${RAN_LOG_REF_DIR}` below is that skill's directory.

## Phase A — inventory

```bash
python3 ${RAN_LOG_REF_DIR}/scripts/correlate/resolve.py <run-dir>
```

Note which components and artifacts are present and their clock anchors. This
drives everything below.

## Phase B — per-artifact summaries

For each component present, use the matching `ran-log-reference` type, then produce
the per-artifact overview here using that type's summary script (follow its
`references/<type>/analysis-guide.md` § Producing an overview):

- OCUDU app component → `ocudu` (run
  `${RAN_LOG_REF_DIR}/scripts/ocudu/ocudu_log_summary.py` on the `gnb.log`/run dir)
- `amarisoft-ue-*` → `amari-ue` (run `${RAN_LOG_REF_DIR}/scripts/amari-ue/ue_log_summary.py`)
- `*.pcap` present → `pcap` (run `${RAN_LOG_REF_DIR}/scripts/pcap/pcap_overview.py` on the run dir's pcaps)
- `amarisoft-5gc-*` → light-touch here: grep `mme.log` for registration /
  PDU-session / NGAP / `[E]` lines (cap at 200 lines); note the future
  `amari-5gc` type.

Capture one headline per component; don't dump raw per-artifact detail.

## Phase C — cross-source alignment

```bash
python3 ${RAN_LOG_REF_DIR}/scripts/correlate/align_clocks.py <run-dir>
```

`align_clocks` checks log↔pcap (the gNB writes its own pcaps → Δ≈0 by
construction; a sanity / display-TZ guard) and UE↔gNB PHY slot alignment.
Cross-process/off-host sources (VIAVI tester, remote 5GC, a UE sim on another box)
may be offset by seconds to hours — measure their offset before comparing
wall-clocks. Surface a non-trivial offset as an anomaly; the (SFN.slot, RNTI) join
doesn't depend on it.

## Phase D — consolidated overview block

Present one block:

```
## OCUDU Run Overview

**Path:** <run-dir>
**Components:** gNB (<build>), UE (<n> UEs), 5GC (<type>), pcaps: <list>
**Clocks:** all UTC; log↔pcap Δ <x> ms; UE↔gNB PHY slots aligned

### Per-component (from ran-log-reference)
- gNB:  <one-line headline from ocudu>
- UE:   <one-line headline from amari-ue>
- pcap: <one-line headline from pcap>
- 5GC:  <registration/PDU-session counts; errors>

### Cross-source picture
- Attach/release counts reconciled across UE ↔ gNB ↔ pcap
- Radio: <PUSCH rx-ok / rx-ko / contention from correlate_radio.py, if run>
- Timeline headline: first PRACH → attach → traffic → release

### Cross-source anomalies
- <bullet per anomaly, or "None">
```

Cross-source anomalies are the value-add — things no single artifact type can see:
- UE reached REGISTERED but the gNB has no matching UE context (or vice-versa).
- pcap shows a release/cause the logs don't, or counts disagree.
- gNB PUSCH `crc=KO` where the UE logged a transmission (real decode issue, not DTX).
- Clock/slot misalignment from `align_clocks.py`.
- UE count vs gNB `UE created` count vs NGAP `InitialUEMessage` count disagree.

## Phase E — optional escalation

If anomalies were found, end with a single `AskUserQuestion`:
- **Investigate** — enter investigation mode on the first anomaly.
- **Query** — ask a specific question.
- **Done** — no further analysis.

Do not ask if the run was clean — end with the overview.
