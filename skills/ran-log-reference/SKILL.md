---
name: ran-log-reference
description: >
  Reference module for RAN test logs and captures — an OCUDU gNB/DU/CU
  log/config/metrics (`gnb.log`, `ocudu_gnb.yml`, `metrics.json`), an Amarisoft UE
  log/config (`ue.log`, `amarisoft_ue.cfg`), an Upper-PDU packet capture
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
helper scripts — for the logs, configs, and captures of an OCUDU/Retina test run.
This skill covers four knowledge **types** — three single-artifact and one cross-artifact —
each with its own subtree:

| Type | Scope | Subtree |
|---|---|---|
| `pcap` | `*.pcap`/`*.pcapng` — Upper-PDU captures (NGAP/F1AP/E1AP/MAC-NR/RLC-NR), usually five siblings (`mac`,`rlc`,`f1ap`,`e1ap`,`ngap`) per run | `references/pcap/`, `scripts/pcap/` |
| `ocudu` | OCUDU `gnb`/`du`/`cu`/`cu_cp`/`cu_up` artifacts: `gnb.log`, `stdout.log`, `ocudu_gnb.yml`, `metrics.json` | `references/ocudu/`, `scripts/ocudu/` |
| `amari-ue` | Amarisoft UE simulator: `ue.log`, `stdout.log`, `amarisoft_ue.cfg` | `references/amari-ue/`, `scripts/amari-ue/` |
| `correlate` | **Cross-artifact**: line up the same event across UE log, gNB log, and pcaps for a whole run — clock/slot alignment, UE-identity joining, PRACH/PUSCH/PUCCH sent-vs-received | `references/correlate/`, `scripts/correlate/` |

This module is **knowledge, not orchestration**. A higher-level inspect/run
*action* skill drives a session (fetching artifacts, choosing a mode, composing
other sources) and calls into this module; the correlation knowledge itself
lives here, in the `correlate` subtree, alongside the per-artifact knowledge it
builds on.

---

## What this skill provides

This is a **knowledge module**, not a task driver. It gives the calling agent
(a higher-level inspect/run orchestrator, or a direct user session) the context
to analyze one artifact. Per type, under `references/<type>/`:

- **`conventions.md`** — the type-specific resolve scoping, efficiency rules, and
  the memory "where things go" routing table. **Read this first** for the type.
- **`analysis-guide.md`** — methodology for the three common activities
  (producing an overview, answering a targeted question, investigating a failure).
- **format refs** (`pcap-format.md` / `log-format.md` / `config-format.md`),
  **`protocols/`** (pcap) and **`procedures/`** — field/filter references and
  per-procedure expected-sequence / failure-marker templates.
- **`scripts/<type>/`** — pre-vetted helper scripts that emit compact summaries.

The general rules below (resolve → read-one, shared efficiency, memory flow)
apply to every type; the per-type `conventions.md` carries only the deltas.

## How to use it

1. **Resolve & classify** the input (§ Resolve & classify) — one script prints
   the artifact `kind` and which `references/<type>/` subtree to read.
2. For a single-artifact type, **read `references/<type>/conventions.md`**, then
   follow `references/<type>/analysis-guide.md` for the activity at hand —
   *Producing an overview*, *Answering a targeted question*, or *Investigating a
   failure*. For `correlate`, start at `references/correlate/cross-correlation.md`
   (the master clock/slot/ID model) and the cross-artifact traces in
   `references/correlate/procedures/`.
3. Apply the shared § Efficiency rules **plus** the type-specific rules in
   `conventions.md` (single-artifact types) throughout.
4. If analysis surfaces a generalisable learning, persist it per § Memory &
   self-maintenance.

**Load only what the kind needs.** Single-artifact work loads just that type's
subtree — never pull a sibling type's `references/` into context. **Correlation**
is the exception by design: it loads `references/correlate/` *and* draws on the
per-artifact subtrees for the sources it joins (`pcap` / `ocudu` / `amari-ue`).

---

## Resolve & classify

One dispatcher classifies the input and runs the matching per-type resolve /
preflight in a single call:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/resolve.py <artifact-or-dir>
```

It classifies the input — a `.pcap`/`.pcapng` or a directory of sibling pcaps →
`pcap`; a `gnb.log` / OCUDU component or run dir → `ocudu`; a `ue.log` /
Amarisoft UE component or run dir → `amari-ue`; a whole run dir spanning **≥2 RAN
application components** (gNB + UE + 5GC) → `correlate` — then delegates to that
kind's resolve script (`scripts/<kind>/resolve.py`). It prints the resolved
`kind`, the `-> read references/<type>/` pointer, the per-kind inventory/
validation, and a final `verdict:` line. **Bail if the verdict is not OK.** When
the input matches no kind, it says so — ask the user rather than guessing.

For the per-type scoping notes (multi-component run dirs, sibling-pcap scope,
Upper-PDU dissector preflight), see `references/<type>/conventions.md`.

---

## Efficiency rules (shared)

These hold for every type; `references/<type>/conventions.md` adds the deltas.

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

When analysis surfaces a generalisable learning — or reveals a doc/script is
wrong — propose the change and apply it **only after the user approves**, editing
**only files inside this skill's own `references/<type>/` and `scripts/<type>/`
trees**. Never touch files elsewhere, and never git/commit — edits are left as
diffs.

- **Where things go** is type-specific: for a single-artifact type, see the
  routing table in `references/<type>/conventions.md` (§ Memory routing). A
  **cross-artifact** learning (clock/slot alignment, identifier joining, a
  multi-source procedure trace) goes in `references/correlate/` —
  `cross-correlation.md`, `ue-identity-map.md`, or a `correlate/procedures/*.md`;
  a correlation-script fix goes in `scripts/correlate/`.
- **For every edit**: propose the path + section + exact diff → confirm via
  `AskUserQuestion` (**Apply** / **Edit wording** / **Skip**) → apply on approval
  → for a `.py` change run `python3 -m py_compile` (re-run on the input when
  practical) → report what changed.
- **Never** save run-specific values (RNTIs, UE-IDs, AMF UE NGAP IDs, frame
  numbers, timestamps, PCIs, KPIs, per-run narratives) — those don't generalise.
  Operator-/preference-level knowledge goes to the project auto-memory under
  `~/.claude/projects/<project-key>/memory/`, not `references/`.

**Maintenance trigger**: on "reorganize <type> knowledge" (e.g. "reorganize pcap
knowledge"), re-read all of `references/<type>/`, dedupe, fix stale tshark/grep
syntax, and report a one-paragraph summary — each edit under the confirm flow.
