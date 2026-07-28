# Overview mode (playbook)

Produce one consolidated, factual overview: summarize each artifact through its
own type, then add the cross-source layer on top. **Do not** enter the
investigation loop. Ask `AskUserQuestion` only at the end (escalation).

Generic mechanics live here; the per-type specifics (which summary script, which
summary-block template) live in `references/<kind>/overview.md`. Substitute
`${CLAUDE_SKILL_DIR}` inline in commands — the shell doesn't persist env vars
between calls.

## Conduct

- **Factual, not diagnostic.** Report what the artifacts show. A suspicious
  signal is an *anomaly bullet*, not a root cause — escalating is Phase E's job.
- Run the scripts; **never** read a raw log or pcap into context.
- One headline per component. Don't dump per-artifact detail into the overview —
  the value is the consolidated picture.
- Everything the scripts emit lands in the session cache. A later mode
  (`mode-query.md` / `mode-investigate.md`) **reuses** it rather than re-running.

## Phase A — inventory

Resolve the input if not already done (`SKILL.md` § Resolve & classify). For a
whole run, that is:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/resolve.py <run-dir>
```

Note which components and artifacts are present and their clock anchors. This
drives everything below. A single-artifact input skips straight to Phase B for
its one type.

## Phase B — per-artifact summaries

For **each component present**, read that type's slot and follow it:

```
references/<kind>/overview.md
```

It names the summary script to run and the summary-block template to fill.
Map component → kind with the table in `SKILL.md` § Resolve & classify
(`ocudu-*` → `ocudu`, `amarisoft-ue-*` → `amari-ue`, `*.pcap` → `pcap`,
`*_Command_Log*` → `viavi`).

`amarisoft-5gc-*` has no type yet — light-touch only: grep `mme.log` for
registration / PDU-session / NGAP / `[E]` lines, capped at 200 lines.

Capture one headline per component.

## Phase C — cross-source alignment

Only when ≥2 components are present. Read `references/correlate/overview.md` and
follow it — it owns the clock/slot alignment step and the list of cross-source
anomalies that no single artifact can reveal.

## Phase D — consolidated overview block

For a **single artifact**, present that type's own summary block from
`references/<kind>/overview.md` and stop.

For a **whole run**, present one consolidated block:

```
## RAN Run Overview

**Path:** <run-dir>
**Components:** gNB (<build>), UE (<n> UEs), 5GC (<type>), pcaps: <list>
**Clocks:** <from references/correlate/overview.md>

### Per-component
- gNB:  <one-line headline>
- UE:   <one-line headline>
- pcap: <one-line headline>
- 5GC:  <registration/PDU-session counts; errors>

### Cross-source picture
- <reconciled counts, radio summary, timeline headline>

### Anomalies
- <bullet per anomaly, or "None">
```

Per-component headlines come from Phase B; the cross-source picture and its
anomalies come from Phase C.

## Phase E — optional escalation

If anomalies were found, end with a single `AskUserQuestion`:

- **Investigate** — read `mode-investigate.md` and enter it on the first anomaly,
  reusing the cached script output from Phase B/C (don't re-run).
- **Query** — read `mode-query.md` and answer a specific question.
- **Done** — no further analysis.

Do not ask if the run was clean — end with the overview.

## Persist learnings

Only if the session surfaced something generalisable — route it per
`references/self-maintenance.md`.
