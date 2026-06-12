# OCUDU gNB log analysis guide

Methodology for the three common gNB-log analysis activities. This is reference
knowledge for whoever holds the context (a higher-level inspect/run orchestrator
skill or a direct user session) — pick the section that matches the task. It assumes the
input has already been resolved to a run directory (see `SKILL.md` § Resolve) and
that the § Efficiency rules apply throughout.

---

## Producing an overview

Produce a factual summary of the run without diving into individual log lines.

### inventory

The § Resolve step already reported the run dir and which of `gnb.log`,
`stdout.log`, `ocudu_gnb.yml`, `metrics.json` are present. Also note any sibling
`*.pcap` (defer those to `analyze-pcap`) and multi-component setups (a sibling
`ocudu-cu-cp-*/` or `ocudu-du-*/` means the analysis lives in *this* component
only — don't try to merge them in an overview).

### run summary script

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu_log_summary.py <run-dir>
```

The script emits, in one pass:

- Build info (commit, branch, build mode) and binary identity.
- Cell config(s) — pci, band, BW, ARFCN, dl/ul freq, antennas.
- AMF endpoint and NG setup outcome (`success` / `failure (cause=...)`).
- Run start/end time and duration.
- Enabled log layers (derived from `ocudu_gnb.yml` overrides).
- Procedure counts: UE creations/releases, RRC reconfigurations, handovers
  (`reconfigurationWithSync` body present), reestablishments, PRACH attempts,
  PHY CRC failures, bearer setups/releases.
- Aggregate scheduler metrics (peak DL/UL bitrate, max latency, late HARQs,
  failed PDCCH/UCI counts).
- Shutdown disposition: clean (`Workers stopped successfully`) vs abnormal.
- Anomalies detected: warnings/errors in `gnb.log`, NGAP failures, msg3 NACKs,
  late HARQs > 0, RRC release without prior `UEContextReleaseCommand`.

If the script is not present or fails, fall back to the grep recipes in
`references/log-format.md` § Key grep recipes to collect the same info manually.

### stdout quick-scan

`stdout.log` is short for single-UE runs — read it in full to capture:

- gNB version banner (`OCUDU gNB (commit ...)`).
- Per-cell freq config lines.
- `N2: Connection to AMF on ...` success/failure.
- `==== gNB started ===` (start marker) presence.
- Final `Stopping...` / `Logfile stored in ...` / `RLC PCAP stored in ...`
  lines (absence ⇒ abnormal exit).

For multi-UE runs `stdout.log` reprints the metrics table many times — use
`head -n 50` + `tail -n 30` instead of `cat`.

### summary block

Present to the user as a single structured block:

```
## OCUDU gNB Run Overview

**Path:** <run-dir>
**Test:** <parent test dir name, if visible>
**Build:** commit <sha> on branch <branch>

### Configuration
- gNB ID: <id> · RAN node: <name>
- Cells: pci=<N> band=n<X> BW=<Y> MHz <T>T<R>R dl_arfcn=<A> dl_freq=<F> MHz
- AMF: <ip>:<port> (NG setup: success | failure cause=<X>)
- Log levels enabled: rrc=<L>, ngap=<L>, f1ap=<L>, pdcp=<L>, mac=<L>, phy=<L>
- PCAPs: rlc, ngap, f1ap, e1ap, mac (only the ones enabled)
- Duplex: TDD <pattern> | FDD

### Timeline
- <time>  gNB started (AMF connected)
- <time>  ue=0 c-rnti=0x4601 created  (Initial Context Setup → DRB up)
- <time>  Handover ue=0 cell pci=1 → pci=2     ← if any
- <time>  ue=0 released (cause from NGAP UEContextReleaseCommand)
- <time>  gNB stopped (clean)

### Procedures
- UE attaches:    N
- RRC reconfig:   N
- Handovers:      N
- Reestablishments: N
- Bearer setups:  N    releases: N
- PRACH events:   N    PHY CRC failures: N
- Warnings:       N    Errors: N

### Traffic (peak per cell)
- pci=1: DL <X> Mbps · UL <Y> Mbps · BLER DL <Z>% UL <Z>%
- pci=2: ...

### Anomalies
- <bullet per anomaly, or "None">
```

---

## Answering a targeted question

Answer one specific question about the run. Stay tight.

### restate and scope

Restate the question in one sentence. Identify:
- Which file(s) to search (`gnb.log`, `stdout.log`, `ocudu_gnb.yml`,
  `metrics.json`).
- Which grep pattern or script flag answers it.
- Whether scoping by UE (`ue=N` on CU side, `c-rnti=0xNNNN` on DU side) or by
  cell (`pci=N`) is needed.

If scope is genuinely ambiguous (multi-UE run with no UE named, multi-cell run
with no cell named, a time window that isn't specified), the caller should
clarify scope before running broad searches. Helpers for listing candidates:
- UEs: `grep -oE 'ue=[0-9]+ c-rnti=0x[0-9a-f]{4}: UE created' gnb.log | sort -u`
- cells: `grep -oE 'pci=[0-9]+' gnb.log | sort -u`

### execute

Use the search script first when it fits:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu_log_search.py <gnb.log> \
  [--layer <RRC|NGAP|F1AP|E1AP|MAC|SCHED|PHY|PDCP|CU-CP|CU-UP|DU|...>] \
  [--ue <N>] \
  [--rnti <hex>] \
  [--pci <N>] \
  [--after <HH:MM:SS.mmm>] \
  [--before <HH:MM:SS.mmm>] \
  [--pattern <regex>] \
  [--count] \
  [--max-lines 200]
```

Examples for common questions:

| Question | Command |
|---|---|
| "How many handovers?" | `--pattern reconfigurationWithSync --count` |
| "When did the UE attach?" | `--layer RRC --pattern "DCCH UL rrcSetupComplete"` |
| "When did NGAP connect to AMF?" | `--pattern "NGSetupResponse\|NGSetupFailure"` |
| "All PRACH events" | `--layer SCHED --pattern "prach\("` |
| "Cells configured?" | `--pattern "Cell creation idx="` |
| "Final RRC release?" | `--layer RRC --pattern "rrcRelease"` |
| "Bearer setups?" | `--pattern "BearerContextSetupResponse" --count` |
| "Which band/BW used?" | read `ocudu_gnb.yml` or `grep "^Cell pci=" stdout.log` |
| "How long did the run last?" | `--pattern "Built in\|Workers stopped successfully"` |
| "Any errors or warnings?" | `--level "E|W|C"` |
| "Did the UE complete attach?" | `--layer CU-CP --pattern '"Initial Context Setup Routine" finished'` |
| "Reestablishment seen?" | `--pattern "rrcReestablishment"` |

Otherwise, use targeted grep with the canonical recipes in
`references/log-format.md` § Key grep recipes. Always cap with `| head -n 200`;
if a result is larger, narrow it (time window, UE id, cell) or spill into the
session cache dir as `gnb-query-<sha>.txt` and report the path (see SKILL.md
§ Efficiency rules).

**YAML/config questions** — look at **both** `ocudu_gnb.yml` (what the user/Retina
supplied; search top-to-bottom because of duplicate-key, last-wins behaviour) and
the `[CONFIG  ] [D] Input configuration` echo at the top of `gnb.log` (the
effective value after defaults and merges). Mention both if they differ.

**Metrics questions** — for "max throughput", "BLER", "any late HARQs", parse
`metrics.json` with python; never `cat` it whole. The summary script does the
common rollups already — prefer it.

### answer

Reply concisely:

- Direct answer in the first sentence.
- Supporting evidence: log line number(s), timestamp(s), the grep/script used.
- If unanswerable from the available files, say so and list what was tried.

Example:

```
**Answer:** The UE attached at 18:18:30.803 (gnb.log:758).

Evidence:
  18:18:30.803 [RRC] DCCH UL rrcSetupComplete           (line 758)
  18:18:30.952 [CU-CP] "Initial Context Setup Routine" finished successfully (line 890)

Commands used:
  grep -nE "DCCH UL rrcSetupComplete|Initial Context Setup Routine.*finished" gnb.log
```

---

## Investigating a failure

Drive a root-cause investigation of the run.

### symptom

Establish the symptom in one short paragraph:

- Which run directory and component (`ocudu-gnb-*` vs `ocudu-cu-*` vs `ocudu-du-*`).
- Which UE (if known) and how it's identified — `ue=N` on CU side, or the
  `c-rnti=0xNNNN` on the DU side, or `amf_ue_ngap_id` on the AMF/NGAP side.
- What the expected behaviour was vs. what was observed.
- Approximate timestamp window (from the procedure timeline produced by the
  summary script, or from `[METRICS]` rows).

If the summary script has not been run yet for this input, run it now:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu_log_summary.py <run-dir>
```

Treat anomalies it flagged (warnings/errors, late HARQs, NGAP setup failure,
RRC reestablishment, msg3 NACKs, abnormal shutdown, dropped traffic) as primary
leads.

### first hypothesis — procedure dispatch

Match the symptom to the most likely procedure file:

| Symptom | File |
|---|---|
| UE never attached (no `UE created` or no `Initial Context Setup Routine finished`) | `procedures/ue-attach.md` |
| UE attached but no data / DRB never set up | `procedures/pdu-session-setup.md` |
| Handover triggered but failed (no `rrcReconfigurationComplete` on target, or RLF after `reconfigurationWithSync`) | `procedures/handover.md` |
| RRC reestablishment seen (`rrcReestablishmentRequest`) | `procedures/reestablishment.md` |
| UE released unexpectedly | `procedures/ue-release.md` |
| NGAP / AMF connection lost or never established | `procedures/ngap-setup.md` |
| PHY-only failures (PRACH undecoded, persistent `crc=KO`, ZMQ rx waiting) | `procedures/phy-issues.md` |
| Throughput regression / late HARQs / failed PDCCH | `procedures/throughput-degradation.md` |
| Process crashed / abnormal exit | `procedures/abnormal-exit.md` |

Load the matching file and follow its expected-sequence checklist.

If no procedure file matches, fall back to the layered approach:
1. Identify the **last successful** layer-level event before the symptom.
2. Identify the **first divergent** event after it.
3. The gap is your hypothesis space.

### investigation loop

Repeat until the diagnosis is clear:

1. Pick the **next smallest check** that can confirm or refute the current
   hypothesis. Use grep or the search script — never read raw `gnb.log` into
   context.
2. Run it. Apply the efficiency rules from `SKILL.md`.
3. Decide whether the result is **meaningful**:
   - Locates a specific failure event in time and layer, OR
   - Confirms or refutes the current hypothesis, OR
   - Opens a new lead in a different layer, UE, or peer component.
   Intermediate results that don't change the picture feed silently into the
   next check.
4. On a **meaningful** finding, record it as:

   ```
   **Found:** <one sentence — layer, timestamp, log line excerpt, what it shows>
   **Clues so far:**
     - <bullet>
     - <up to 5 total>
   **Next:** <exact grep/script command you intend to run>
   **Why:** <one sentence — which hypothesis this supports or refutes>
   ```

### cross-artifact escalation

When the symptom is on the UE side or on the air interface, the OCUDU log alone
is insufficient — pull in the relevant sibling knowledge:

- `analyze-amari-ue-log` if a sibling `amarisoft-ue-*/` directory exists — the
  UE-side log shows MIB/SIB decoding, PRACH transmission, RRC state machine.
- `analyze-pcap` if any sibling `*.pcap` exists in the same run dir —
  F1AP/E1AP/NGAP body details are richer in pcap.

Reach for these when current clues plateau, not before.

### final diagnosis

When the hypothesis is confirmed, produce a single closing block:

```
## Diagnosis

- **What worked:** <procedures that completed normally>
- **What failed:** <layer, timestamp, log line excerpt>
- **Root cause:** <one paragraph in NR/5G protocol terms, naming the specific
  message / counter / config knob>
- **Key log evidence:**
  - `<timestamp> [LAYER] <excerpt>` (line N) — <why it matters>
  - ...
- **Suggested next steps:**
  - <which sibling artifact to cross-correlate (UE log, PCAP, AMF log)>
  - <which config knob to tune, which test variant to re-run>
```

---

## Persisting learnings

If an activity surfaces a generalisable learning (a reusable grep recipe, a new
failure signature, a log/config detail), persist it via the flow in `SKILL.md`
§ Memory & self-maintenance — weave it into the natural section, or create a new
procedure/script file if warranted.
