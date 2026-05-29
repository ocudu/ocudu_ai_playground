# Overview mode

Produce a factual summary of the OCUDU gNB run without diving into individual
log lines. Do not ask `AskUserQuestion` mid-flow unless an anomaly merits
escalation.

## Phase A — inventory

```bash
ls -lh <run-dir>
wc -l <run-dir>/gnb.log
```

Check which files are present: `gnb.log`, `stdout.log`, `ocudu_gnb.yml`,
`metrics.json`, any `*.pcap`. Note multi-component setups (a sibling
`ocudu-cu-cp-*/` or `ocudu-du-*/` means the analysis lives in *this*
component only — don't try to merge them in overview mode).

## Phase B — run summary script

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/ocudu_log_summary.py <run-dir>
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
`references/log-format.md` § Key grep recipes to collect the same info
manually.

## Phase C — stdout quick-scan

`stdout.log` is short for single-UE runs — read it in full to capture:

- gNB version banner (`OCUDU gNB (commit ...)`).
- Per-cell freq config lines.
- `N2: Connection to AMF on ...` success/failure.
- `==== gNB started ===` (start marker) presence.
- Final `Stopping...` / `Logfile stored in ...` / `RLC PCAP stored in ...`
  lines (absence ⇒ abnormal exit).

For multi-UE runs `stdout.log` reprints the metrics table many times — use
`head -n 50` + `tail -n 30` instead of `cat`.

## Phase D — summary block

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

## Phase E — optional escalation

If the summary surfaced one or more anomalies, end with a single
`AskUserQuestion`:

- **Investigate** — enter investigation mode on the first anomaly.
- **Query** — ask a specific question.
- **Done** — no further analysis needed.

Do **not** ask if the run was clean. End the turn with the summary.
