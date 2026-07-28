# VIAVI command-log analysis guide

Methodology for the three common VIAVI-log activities. This is reference
knowledge for whoever holds the context (a higher-level inspect/run orchestrator
or a direct user session) — pick the section that matches the task. It assumes
the input has been resolved to a command-log file (see `SKILL.md` § Resolve) and
that the § Efficiency rules apply throughout.

---

## Producing an overview

Produce a factual summary without diving into individual log lines.

### run summary script

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/viavi/viavi_log_summary.py <command-log>
```

One streaming pass (handles `.txt` and `.zip`) emitting:

- **Test setup** — time span + duration, system contexts (`SCXT`), MTS mode,
  RUs that reached `CU PLANE ACTIVE`, SCS index, Cell IDs, DL frequencies.
- **UE population** — distinct `UE Id` count and range.
- **Random access** — Initiated / Complete / Error / Cancelled counts, completion
  rate, and the breakdown of error `Result` reasons.
- **Connection / registration** — CONNECTION / DISCONNECTION / CONNECTION FAILED /
  REGISTRATION / DEREGISTRATION / PDU-session-modification IND tallies.
- **Mobility** — Handover Complete and Connection Re-establishment counts.
- **Throughput / BLER** — GETSTATS dump count, per-UE stat records, peak DL/UL
  average throughput (bits/s) and max DL/UL SCH BLER across all dumps.
- **Errors / warnings** — failed command responses, TMAE warnings, RLC max-retx.
- **Anomalies** — RA errors, CONNECTION FAILED, RLC max-retx, non-`0x00` responses.

If the script is unavailable, fall back to the grep recipes in
`reference/log-format.md`.

### summary block

Present as a single structured block:

```
## VIAVI Command-Log Overview

**Path:** <command-log>

### Setup
- Duration: Xh Ym  (HH:MM:SS → HH:MM:SS)
- Contexts: 0:LTE, 1:NR   RUs: RU1, RU2 (CU PLANE ACTIVE)
- SCS index N, Cell IDs …, DL freq … MHz

### UEs & lifecycle
- Distinct UE Ids: N (range a–b)
- RA: I initiated / C complete (P%) / E error / X cancelled
- Connection: conn / disc / failed ; Registration: reg / dereg
- Mobility: H handovers, R reestablishments

### Throughput / BLER
- GETSTATS dumps: D ; peak DL/UL avg tput; max DL/UL BLER

### Anomalies
- <bullet per anomaly, or "None">
```

---

## Answering a targeted question

Restate the question in one sentence, then identify the `UE Id` / event / time
window to scope by. Use the search script first when it fits:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/viavi/viavi_log_search.py <command-log> \
  [--ue <id>] \
  [--event <substr>] \
  [--after <HH:MM:SS:mmm>] \
  [--before <HH:MM:SS:mmm>] \
  [--pattern <regex>] \
  [--count] \
  [--max-lines 200]
```

| Question | Command |
|---|---|
| "How many UEs registered?" | `--event "NR REGISTRATION IND" --count` |
| "Did any random access fail?" | `--event "Random Access Error" --count` |
| "Show everything for UE 113" | `--ue 113` |
| "When did UE 113 first connect?" | `--ue 113 --event "NR CONNECTION IND"` |
| "Any connection failures?" | `--event "NR CONNECTION FAILED IND"` |
| "Handovers in a time window" | `--event "Handover Complete" --after … --before …` |
| "Did the RUs come up?" | `--pattern "CU PLANE ACTIVE"` |
| "RLC retransmission limit hit?" | `--pattern "maximum retransmissions"` |
| "Any failed tester commands?" | `--pattern "C: [A-Z_]+ 0x(?!00)"` |

Note `--event` is a substring filter on `I: CMPI` lines — use the precise form
(`"NR REGISTRATION IND"`, not `"REGISTRATION IND"`, which also matches
`DEREGISTRATION IND`). Otherwise use the canonical greps in
`reference/log-format.md` § Key grep recipes; cap with `| head -n 200` and spill
larger results to
`viavi-query-<sha>.txt` (see `SKILL.md` § Efficiency rules).

### answer

- Direct answer first sentence.
- Supporting evidence: timestamp(s) and the script/grep used.
- If unanswerable from the log, say so and list what was tried.

---

## Investigating a failure

### symptom

Establish the symptom in one short paragraph: which `UE Id` (decimal, e.g.
`113`), expected vs observed behaviour, and an approximate time window. Run the
summary script first if it hasn't been run; treat its **Anomalies** as primary
leads.

### first hypothesis — procedure dispatch

| Symptom | File |
|---|---|
| UE never connected / `CONNECTION FAILED IND` | `troubleshooting/ue-attach.md` |
| UE connected but never `REGISTRATION IND` | `troubleshooting/ue-attach.md` |
| Random-access errors (`Max_Preambles_Exceeded`) | `troubleshooting/random-access.md` |
| Reestablishments / handover churn | `troubleshooting/random-access.md` (RA-triggered reest) |
| Low throughput / high BLER | `troubleshooting/throughput.md` |

Load the matching file and follow its failure markers / investigation checklist.
Each per-procedure playbook cites its `reference/` expected-sequence sibling
(`reference/<proc>.md`) for the normal message ladder to compare against.

### investigation loop

Repeat until the diagnosis is clear:

1. Pick the **next smallest check** that confirms or refutes the current
   hypothesis — `viavi_log_search.py` scoped by `--ue` / `--event` / time window.
2. Run it; apply the efficiency rules.
3. On a **meaningful** finding (locates a failure in time, or confirms/refutes a
   hypothesis), record it:

   ```
   **Found:** <one sentence — event, timestamp, log excerpt, what it shows>
   **Clues so far:**
     - <bullet, up to 5>
   **Next:** <exact search/grep command>
   **Why:** <which hypothesis it tests>
   ```

### final diagnosis

```
## Diagnosis

- **What worked:** <procedures that completed normally>
- **What failed:** <event, timestamp, log excerpt>
- **Root cause:** <one paragraph in NR/5G terms>
- **Key log evidence:**
  - `<timestamp> I: CMPI <excerpt>` — <why it matters>
- **Suggested next steps:**
  - <which OCUDU gNB log / pcap to cross-check; what to compare>
```

Because the VIAVI log is the *tester's* view, a failure here usually needs the
OCUDU gNB log or a pcap to confirm the network-side cause — name what to compare.

---

## Persisting learnings

If an activity surfaces a generalisable learning (a reusable grep recipe, a new
event signature, a failure pattern), persist it via `SKILL.md` § Memory &
self-maintenance — into the natural section, or a new procedure/script file.
