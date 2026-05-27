# Overview mode

Produce a factual summary of the UE run without diving into individual log lines.
Do not ask `AskUserQuestion` mid-flow unless an anomaly merits escalation.

## Phase A — inventory

```bash
ls -lh <run-dir>
wc -l <run-dir>/ue.log
```

Check which files are present: `ue.log`, `stdout.log`, `amarisoft_ue.cfg`, `metrics.json`.

## Phase B — run summary script

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/ue_log_summary.py <run-dir>
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

## Phase C — stdout quick-scan

`stdout.log` is short — read it in full to capture:

- UE version
- RF port configuration (frequencies, bands)
- Cell(s) SIB found
- Final CBR stats

## Phase D — summary block

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

## Phase E — optional escalation

If the summary surfaced one or more anomalies, end with a single `AskUserQuestion`:

- **Investigate** — enter investigation mode on the first anomaly.
- **Query** — ask a specific question.
- **Done** — no further analysis needed.

Do **not** ask if the run was clean. End the turn with the summary.
