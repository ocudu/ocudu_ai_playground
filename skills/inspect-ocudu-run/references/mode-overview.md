# Overview mode

Produce one consolidated, factual overview of the whole run by delegating each
artifact to its sub-skill and adding the cross-source layer on top. Do not enter
the investigation loop. Ask `AskUserQuestion` only at the end (escalation).

## Phase A — inventory

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/run_inventory.py <run-dir>
```

Note which components and artifacts are present and their clock anchors. This
drives everything below.

## Phase B — per-artifact summaries (delegate)

For each component present, invoke its sub-skill in **overview mode** via the
`Skill` tool and collect the returned summary:

- OCUDU app component → `analyze-ocudu-gnb-log` (overview of the `gnb.log`/run dir)
- `amarisoft-ue-*` → `analyze-amari-ue-log` (overview)
- `*.pcap` present → `analyze-pcap` (overview of the run dir's pcaps)
- `amarisoft-5gc-*` → light-touch here: grep `mme.log` for registration /
  PDU-session / NGAP / `[E]` lines (cap at 200 lines); note the future
  `analyze-amari-5gc-log` hook.

Keep each sub-skill's output as-is; don't re-derive per-artifact detail.

## Phase C — cross-source alignment

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/align_clocks.py <run-dir>
```

Confirm the sources share UTC (log↔pcap Δ≈0) and that UE↔gNB PHY slots align.
If `align_clocks` reports an unexpected offset, surface it as an anomaly — every
later correlation depends on it.

## Phase D — consolidated overview block

Present one block:

```
## OCUDU Run Overview

**Path:** <run-dir>
**Components:** gNB (<build>), UE (<n> UEs), 5GC (<type>), pcaps: <list>
**Clocks:** all UTC; log↔pcap Δ <x> ms; UE↔gNB PHY slots aligned

### Per-component (from sub-skills)
- gNB:  <one-line headline from analyze-ocudu-gnb-log>
- UE:   <one-line headline from analyze-amari-ue-log>
- pcap: <one-line headline from analyze-pcap>
- 5GC:  <registration/PDU-session counts; errors>

### Cross-source picture
- Attach/release counts reconciled across UE ↔ gNB ↔ pcap
- Radio: <PUSCH rx-ok / rx-ko / contention from correlate_radio.py, if run>
- Timeline headline: first PRACH → attach → traffic → release

### Cross-source anomalies
- <bullet per anomaly, or "None">
```

Cross-source anomalies are the value-add — things no single sub-skill can see:
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
