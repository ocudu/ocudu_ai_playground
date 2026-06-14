# Amarisoft UE log analysis guide

Methodology for the three common UE-log analysis activities. This is reference
knowledge for whoever holds the context (a higher-level inspect/run orchestrator
skill or a direct user session) — pick the section that matches the task. It assumes the
input has already been resolved to a run directory (see `SKILL.md` § Resolve) and
that the § Efficiency rules apply throughout.

---

## Producing an overview

Produce a factual summary of the UE run without diving into individual log lines.

### inventory

The § Resolve step already reported the run dir and which of `ue.log`,
`stdout.log`, `amarisoft_ue.cfg` are present.

### run summary script

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/amari-ue/ue_log_summary.py <run-dir>
```

The script emits, in one pass:

- UE configuration (band, BW, UE count, IMSI, sim events)
- Run start/end time and duration
- UE software version and RF port info
- NAS state timeline (deduped, state changes only)
- Key RRC messages (setup, reconfigurations, reestablishments)
- Procedure counts: PRACH attempts, handovers, reestablishments, PHY CRC failures
- Traffic stats: CBR sent/received with loss percentage
- Sim events timeline (power_on, cbr_start, power_off, quit)
- Anomalies detected (packet loss > 1%, PHY errors, unexpected final NAS state)

If the script is not yet present or fails, fall back to the grep recipes in
`references/log-format.md` to collect the same information manually.

### stdout quick-scan

`stdout.log` is short — read it in full to capture:

- UE version
- RF port configuration (frequencies, bands)
- Cell(s) SIB found
- Final CBR stats

### summary block

Present to the user as a single structured block:

```
## Amarisoft UE Run Overview

**Path:** <run-dir>
**Test:**  <parent test dir name, if visible>

### Configuration
- UE count: N [single-UE | multi-UE]
- Band: nXX, BW: YY MHz
- Sim events: power_on → cbr_recv/send → power_off → quit
- UE version: 2025-09-19

### Timeline
- <time>  Started
- <time>  [UE 0001] 5GMM-REGISTERED CM-CONNECTED
- <time>  Handover (cell 00 → 01)     ← if any
- <time>  [UE 0001] 5GMM-NULL CM-IDLE
- <time>  Ended (duration: Xs)

### Procedures
- PRACH: N attempts
- Handovers: N
- Reestablishments: N
- PHY CRC failures: N

### Traffic
- DL: sent=N, recv=M (X.X% loss)
- UL: sent=N, recv=M (X.X% loss)

### Anomalies
- <bullet per anomaly, or "None">
```

---

## Answering a targeted question

Answer one specific question about the UE run. Stay tight.

### restate and scope

Restate the question in one sentence. Identify:
- Which file(s) to search (`ue.log`, `stdout.log`, `amarisoft_ue.cfg`).
- Which grep pattern or script flag answers it.
- Whether scoping by UE ID or cell ID is needed.

If scope is genuinely ambiguous (a multi-UE run with no UE named, a time window
that isn't specified), the caller should clarify scope before running broad
searches. List candidate UE IDs (hex) with
`grep -oE ' [0-9a-f]{4} New state' ue.log | sort -u`.

### execute

Use the search script first when it fits:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/amari-ue/ue_log_search.py <ue.log> \
  [--layer <NAS|RRC|PHY|MAC|PROD>] \
  [--ue <ue_id>] \
  [--cell <cell_id>] \
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
| "When did UE attach?" | `--layer NAS --pattern "REGISTERED\s+CM-CONNECTED"` |
| "All PRACH attempts" | `--layer PHY --pattern "PRACH:"` |
| "What cells did the UE see?" | `--layer PHY --pattern "PSS:"` |
| "Was there packet loss?" | grep `CBR_RECV\|CBR_SEND` in `stdout.log` |
| "What was the final NAS state?" | `--layer NAS` then tail |
| "Did the UE reestablish?" | `--pattern "reestablishment" --layer RRC` |
| "What band/BW was used?" | read `amarisoft_ue.cfg` or `grep "^RF" stdout.log` |
| "How long did the run last?" | `grep -E "^# (Started|Ended)" ue.log` |

Otherwise, use targeted grep with the canonical recipes in
`references/log-format.md` § Key grep recipes. Always cap with `| head -n 200`;
if a result is larger, narrow it (time window, UE ID) or spill into the session
cache dir as `amari-query-<sha>.txt` and report the path (see SKILL.md
§ Efficiency rules).

### answer

Reply concisely:

- Direct answer first sentence.
- Supporting evidence: log line number(s), timestamp(s), the grep/script used.
- If unanswerable from the available files, say so and list what was tried.

---

## Investigating a failure

Drive a root-cause investigation.

### symptom

Establish the symptom in one short paragraph:

- Which run directory and UE component.
- Which UE ID (if known) and how it's identified (4-char hex UE_ID in log, e.g.
  `0001`, `000a`).
- What the expected behaviour was vs. what was observed.
- Approximate timestamp window (from NAS state timeline or stdout CBR stats).

If the summary script has not been run yet for this input, run it now:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/amari-ue/ue_log_summary.py <run-dir>
```

Treat anomalies it flagged (packet loss, unexpected final NAS state, PHY errors,
missing `# Ended on`) as primary leads.

### first hypothesis — procedure dispatch

Match the symptom to the most likely procedure from `references/procedures/`:

| Symptom | File |
|---|---|
| UE never attached / stuck before 5GMM-REGISTERED | `procedures/registration.md` |
| UE attached but no data flow / CBR loss high | `procedures/data-session.md` |
| UE attached, HO triggered but CBR loss spike | `procedures/handover.md` |
| UE disconnected unexpectedly / reestablishment seen | `procedures/handover.md` |
| UE deregistered before `power_off` sim event | `procedures/registration.md` |
| PHY failures only (crc=FAIL, PRACH not responding) | `procedures/registration.md` |

Load the matching file and follow its expected-sequence checklist.

### investigation loop

Repeat until the diagnosis is clear:

1. Pick the **next smallest check** that can confirm or refute the current
   hypothesis. Use grep or the search script — never read raw log into context.
2. Run it. Apply the efficiency rules from `SKILL.md`.
3. Decide whether the result is **meaningful**:
   - Locates a specific failure event in time and layer, OR
   - Confirms or refutes the current hypothesis, OR
   - Opens a new lead in a different layer or UE.
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

### final diagnosis

When the hypothesis is confirmed, produce a single closing block:

```
## Diagnosis

- **What worked:** <procedures that completed normally>
- **What failed:** <layer, timestamp, log line excerpt>
- **Root cause:** <one paragraph in NR/5G protocol terms>
- **Key log evidence:**
  - `<timestamp> [LAYER] <excerpt>` — <why it matters>
  - ...
- **Suggested next steps:**
  - <which log/pcap to cross-correlate; what to enable in the config>
```

---

## Persisting learnings

If an activity surfaces a generalisable learning (a reusable grep recipe, a new
failure signature, a log/format detail), persist it via the flow in `SKILL.md`
§ Memory & self-maintenance — weave it into the natural section, or create a new
procedure/script file if warranted.
