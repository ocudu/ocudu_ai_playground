---
name: ran-log-reference
description: >
  Reference module for RAN test logs and captures — an OCUDU gNB/DU/CU
  log/config/metrics (`gnb.log`, `ocudu_gnb.yml`, `metrics.json`), an Amarisoft UE
  log/config (`ue.log`, `amarisoft_ue.cfg`), a VIAVI RU-simulator command log
  (`*_Command_Log*.txt`/`.zip`), an Upper-PDU packet capture
  (`.pcap`/`.pcapng`: NGAP/F1AP/E1AP/MAC-NR/RLC-NR), or **cross-artifact
  correlation** across a whole run (clock/slot alignment, UE-identity joining,
  PRACH/PUSCH sent-vs-received). Detects the kind and loads that subtree's format
  refs, procedure templates, and helper scripts. Provides context, not a task —
  the caller analyzes.
version: 0.1.0
user-invocable: true
allowed-tools: Bash(python3 *ran-log-reference/scripts*), Bash(ls:*), Bash(grep:*), Bash(find:*), Bash(file:*), Bash(stat:*), Bash(wc:*), Bash(head:*), Bash(tail:*), Bash(sed:*), Bash(sort:*), Bash(uniq:*), Bash(awk:*), Bash(comm:*), Bash(capinfos:*), Bash(tshark:*), Bash(realpath:*), Bash(sha256sum:*), Bash(cat:*), Edit, Write
---

# RAN log reference

Reference knowledge — format notes, procedure templates, grep/tshark recipes, and
helper scripts — for the logs, configs, and captures of an OCUDU/Retina test run,
across five **types** (four single-artifact, one cross-artifact), each with its
own subtree:

| Type | Scope | Subtree |
|---|---|---|
| `pcap` | `*.pcap`/`*.pcapng` — Upper-PDU captures (NGAP/F1AP/E1AP/MAC-NR/RLC-NR), usually five siblings (`mac`,`rlc`,`f1ap`,`e1ap`,`ngap`) per run | `references/pcap/`, `scripts/pcap/` |
| `ocudu` | OCUDU `gnb`/`du`/`cu`/`cu_cp`/`cu_up` artifacts: `gnb.log`, `stdout.log`, `ocudu_gnb.yml`, `metrics.json` | `references/ocudu/`, `scripts/ocudu/` |
| `amari-ue` | Amarisoft UE simulator: `ue.log`, `stdout.log`, `amarisoft_ue.cfg` | `references/amari-ue/`, `scripts/amari-ue/` |
| `viavi` | VIAVI RU-simulator (TM500) command/event log: `*_Command_Log*.txt` (or its identical `.zip`) | `references/viavi/`, `scripts/viavi/` |
| `correlate` | **Cross-artifact**: line up the same event across UE log, gNB log, and pcaps for a whole run — clock/slot alignment, UE-identity joining, PRACH/PUSCH/PUCCH sent-vs-received | `references/correlate/`, `scripts/correlate/` |

This is **knowledge, not orchestration**: it gives the calling agent the context
to analyze an artifact but takes no action itself. A higher-level inspect/run
*action* skill drives the session (fetching artifacts, choosing a mode, composing
other sources) and calls in here.

---

## How to use it

1. **Resolve & classify** the input (§ Resolve & classify) — one script prints the
   artifact `kind` and which `references/<type>/` subtree to read.
2. Read that subtree. Under `references/<type>/`:
   - **`conventions.md`** — type-specific resolve scoping, efficiency deltas, and the
     memory routing table. **Read this first.** (`correlate` instead starts at
     `references/correlate/cross-correlation.md`, the master clock/slot/ID model.)
   - **`analysis-guide.md`** — methodology for the three common activities: *producing
     an overview*, *answering a targeted question*, *investigating a failure*.
     (For `correlate`, the cross-artifact traces in `references/correlate/procedures/`.)
   - **format refs** (`pcap-format.md` / `log-format.md` / `config-format.md`),
     **`protocols/`** (pcap), **`procedures/`** — field/filter references and
     per-procedure expected-sequence / failure-marker templates.
   - **`scripts/<type>/`** — pre-vetted helper scripts that emit compact summaries.
3. Apply the shared § Efficiency rules **plus** the type-specific deltas in
   `conventions.md` throughout.
4. If analysis surfaces a generalisable learning, persist it per § Memory &
   self-maintenance.

**Load only what the kind needs** — single-artifact work pulls just that type's
subtree, never a sibling's. `correlate` is the deliberate exception: it loads
`references/correlate/` *and* draws on the per-artifact subtrees it joins
(`pcap` / `ocudu` / `amari-ue`).

---

## Resolve & classify

One dispatcher classifies the input and runs the matching per-type resolve /
preflight in a single call:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/resolve.py <artifact-or-dir>
```

It classifies the input — a `.pcap`/`.pcapng` or a directory of sibling pcaps →
`pcap`; a `gnb.log` / OCUDU component or run dir → `ocudu`; a `ue.log` /
Amarisoft UE component or run dir → `amari-ue`; a `*_Command_Log*.txt`/`.zip` (or
a dir holding one) → `viavi`; a whole run dir spanning **≥2 RAN application
components** (gNB + UE + 5GC) → `correlate` — then delegates to that kind's
resolve script (`scripts/<kind>/resolve.py`). It prints the resolved
`kind`, the `-> read references/<type>/` pointer, the per-kind inventory/
validation, and a final `verdict:` line. **Bail if the verdict is not OK.** When
the input matches no kind, it says so — ask the user rather than guessing.

For the per-type scoping notes (multi-component run dirs, sibling-pcap scope,
Upper-PDU dissector preflight), see `references/<type>/conventions.md`.

---

## Efficiency rules (shared)

These hold for every type; `references/<type>/conventions.md` adds the deltas.

- **Run the helper scripts from within this skill.** The frontmatter
  `allowed-tools` (`Bash(python3 *ran-log-reference/scripts*)`, plus the read-only
  shell tools) pre-authorizes the scripts only while the skill is active. Invoke
  the skill for log/pcap analysis rather than running the scripts ad hoc from the
  main loop — that way they execute without permission prompts, and no
  `settings.json` permission edits are needed.
- **Session cache dir.** All intermediate state (script outputs the agent may
  post-filter, large spills, staged inputs) lives under one per-session,
  user-private directory:
  `${CLAUDE_CODE_TMPDIR:-/tmp}/claude-skills-${CLAUDE_CODE_SESSION_ID}/`. The
  root is keyed by session, so any other skill in the same session (e.g. a
  higher-level orchestrator) can reuse these cached outputs. Write files with a
  **type prefix** — `pcap-`, `ocudu-`, `amari-`, `correlate-` — so the types don't collide.
  Helper scripts create the dir
  lazily; the OS reaps `/tmp` on reboot, so no manual cleanup.
- **Never** read a raw `gnb.log` / `ue.log` / pcap into context — they can be
  tens to hundreds of thousands of lines (or huge frame dumps). Use the per-type
  summary/search scripts, or grep for specific patterns.
- **Cap** any grep / `tshark -T fields` output at ~200 lines (`| head -n 200`);
  spill larger results to `<cache-dir>/<type>-<purpose>-<sha>.{txt,tsv}` and
  report the path.
- **Prefer** the helper scripts in `scripts/<type>/` over hand-crafted grep /
  tshark chains — they are pre-vetted, cache where useful, and emit compact
  summaries instead of raw lines/frames.
- **Reuse** the cache: if a file you'd produce already exists for the same input,
  post-filter it instead of re-running the script.
- In multi-UE runs, scope queries by UE identifier (`ue=N`, `c-rnti=0xNNNN`,
  UE-id) early — the cross-product over UEs is large.

---

## Memory & self-maintenance

When — and **only** when — an analysis session surfaces something to persist (a
generalisable learning, or a doc/script that is wrong/stale), or the user asks to
"reorganize <type> knowledge", **load `references/self-maintenance.md` and follow
it**. It covers what is/isn't worth saving (general guidance vs run-specific
verdicts; branch-only tooling → temp scripts; preferences → project auto-memory),
where each kind goes, and the confirm-before-edit flow.

Guardrails (always): edit only this skill's own `references/<type>/` and
`scripts/<type>/` trees, never elsewhere, and never git/commit — leave diffs.
