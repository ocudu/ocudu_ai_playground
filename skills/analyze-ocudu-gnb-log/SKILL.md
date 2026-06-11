---
name: analyze-ocudu-gnb-log
description: >
  Knowledge module for analyzing OCUDU gNB / DU / CU run artifacts — `gnb.log`
  (the per-layer log), `stdout.log` (console: cell config + metrics table),
  `ocudu_gnb.yml` (the YAML config), and `metrics.json`. Provides the log/config
  format references, per-procedure templates, grep recipes, and helper scripts.
  Invoked by a higher-level inspect/run orchestrator skill when it needs to
  analyze OCUDU app logs, or directly by a user to load gNB-log analysis context
  (trigger phrases: "analyze
  this gnb log", "look at the ocudu log", or a path ending in `gnb.log`,
  `ocudu_gnb.yml`, `stdout.log`, or under `ocudu-gnb-*/`). It provides context
  and methodology; it does not drive an interactive analysis task — the calling
  agent does the work using this knowledge.
version: 0.1.0
user-invocable: true
allowed-tools: Bash(python3 *analyze-ocudu-gnb-log/references*), Bash(ls:*), Bash(grep:*), Bash(find:*), Bash(file:*), Bash(stat:*), Bash(wc:*), Bash(head:*), Bash(tail:*), Bash(sed:*), Bash(sort:*), Bash(comm:*), Bash(realpath:*), Bash(sha256sum:*), Bash(cat:*), Edit, Write
---

# Analyze OCUDU gNB logs

Analyze OCUDU gNB diagnostic logs (`gnb.log`), console output (`stdout.log`),
YAML configuration (`ocudu_gnb.yml`), and scheduler metrics (`metrics.json`)
produced by Retina test runs against the OCUDU `gnb`/`du`/`cu`/`cu_cp`/`cu_up`
binaries. A single run directory typically contains:

| File | Description |
|---|---|
| `gnb.log` | Per-layer protocol trace (CONFIG echo + RRC/NGAP/F1AP/E1AP/MAC/PHY/SCHED/PDCP/GTPU/...) |
| `stdout.log` | Console: banner, cell config, AMF connection, metrics table, shutdown lines |
| `ocudu_gnb.yml` | YAML config the binary was started with (multi-document — sections are concatenated) |
| `metrics.json` | Per-period JSON metrics (one object per record, NDJSON-like) |
| `ps_info_gnb.txt` | Process CPU/memory snapshot (rarely needed) |
| `*.pcap` | Optional protocol captures (`rlc.pcap`, `mac.pcap`, `ngap.pcap`, `f1ap.pcap`, `e1ap.pcap`) — defer to the `analyze-pcap` skill |

The Retina sibling components (`amarisoft-ue-*/`, `amarisoft-5gc-*/`) hold the UE
and core logs. When OCUDU symptoms point at the UE side, hand off to
`analyze-amari-ue-log`.

---

## What this skill provides

This is a **knowledge module**, not a task driver. It gives the calling agent
(usually a higher-level inspect/run orchestrator skill, sometimes a direct user
session) the context needed to analyze OCUDU gNB/DU/CU logs:

- `references/log-format.md` and `references/config-format.md` — the log layout,
  grep recipes, and YAML/config quirks.
- `references/procedures/` — per-procedure expected-sequence / failure-marker /
  investigation-checklist templates.
- `references/scripts/` — pre-vetted helper scripts (`ocudu_log_summary.py`,
  `ocudu_log_search.py`) that emit compact summaries.
- `references/analysis-guide.md` — methodology for the three common activities
  (producing an overview, answering a targeted question, investigating a failure).

## How to use it

1. **Resolve** the input to a run directory (§ Resolve).
2. Follow `references/analysis-guide.md` for the activity at hand — *Producing an
   overview*, *Answering a targeted question*, or *Investigating a failure* —
   leaning on the helper scripts and the format/procedure references.
3. Apply the § Efficiency rules throughout.
4. If analysis surfaces a generalisable learning, persist it per § Memory &
   self-maintenance.

---

## Resolve

One script resolves the input and inventories the run:

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/resolve.py <path>
```

It accepts a `gnb.log` file, a run directory, an `ocudu-gnb-N-M/` component dir,
or a Retina `test_gnb[...]` dir, and resolves to the latest run directory holding
a `gnb.log`. It prints the resolved run dir, the analysis artifacts present
(`gnb.log`, `stdout.log`, `ocudu_gnb.yml`, `metrics.json`), and a `verdict:`
line; it exits non-zero (`BAIL`) if no `gnb.log` is found or it is empty.
**Bail if the verdict is not OK.** (gNB logs are plain text — there is nothing to
validate beyond presence, so this is resolution + inventory, not a preflight.)

**Scope** — when a `test_gnb[...]` dir holds more than one OCUDU app component
(e.g. `ocudu-gnb-1-1` + `ocudu-gnb-1-2`, or a CU/DU split), `resolve.py` reports
them and notes which one it resolved to; scope explicitly to the component you
mean before going further.

---

## Efficiency rules

- **Session cache dir.** Intermediate state (large grep spills, cached script
  outputs that the agent may want to post-filter later) lives under one
  per-session, user-private directory:
  `${CLAUDE_CODE_TMPDIR:-/tmp}/claude-skills-${CLAUDE_CODE_SESSION_ID}/`. It is
  shared with the `analyze-pcap` and `analyze-amari-ue-log` skills so all three
  can cross-reference cached outputs in one run. Create the dir lazily
  (`mkdir -p` via the python helpers) and use the `gnb-` prefix on files you
  write here (e.g. `gnb-summary-<sha>.txt`, `gnb-search-<sha>.txt`). The OS
  reaps `/tmp` on reboot — no manual cleanup needed.
- **Never** read raw `gnb.log` into context — it can be 75k–500k+ lines, and
  the first ~440 lines are the echoed CONFIG dump which adds no signal beyond
  what's in `ocudu_gnb.yml`.
- **Cap** any grep output at 200 lines with `| head -n 200`; for larger results
  write to `<cache-dir>/gnb-<purpose>-<sha>.txt` and report the path.
- **Prefer** the helper scripts in `references/scripts/` over hand-crafted
  grep chains — they emit compact, token-efficient summaries.
- **Reuse** cached output: if a file you'd produce already exists in the cache
  dir for the same input, **post-filter** it (grep, head) instead of re-running
  the script.
- `stdout.log` is short (typically 30–300 lines; longer for multi-UE runs that
  print the metrics table many times) — safe to read in full when single-UE.
  For multi-UE traffic runs, `head -n 50` plus `tail -n 30` is enough.
- `ocudu_gnb.yml` is short (100–200 lines) — safe to read in full. Beware that
  the file is a **concatenation of multiple YAML documents** with no `---`
  separators; later keys override earlier ones (e.g. `all_level: info` then
  `all_level: warning`). See `references/config-format.md`.
- The CONFIG echo at the top of `gnb.log` (everything between line 2 and the
  first `[CONFIG  ] [I] Worker pool` line, typically ~line 440) is verbose and
  redundant with `ocudu_gnb.yml` — skip it unless the user explicitly asks
  about an effective-config value.
- `metrics.json` is a standard JSON array of per-period records — parse it with
  `python3 -c 'import json; json.load(open("metrics.json"))'`, never `cat` it
  into context. The summary script rolls it up already.
- In multi-UE mode, scope grep queries by `ue=N` or `c-rnti=0xNNNN` early.

---

## Memory & self-maintenance

When analysis surfaces a generalisable learning — or reveals a doc/script is
wrong — propose the change and apply it **only after the user approves**, editing
**only files inside this skill's `references/` tree**. Never touch files
elsewhere, and never git/commit — edits are left as diffs.

**Where things go** (match the surrounding format; no dates/timestamps):
- new grep recipe → `log-format.md` § Key grep recipes
- new layer / message / keyword → the matching table in `log-format.md`
  (§ Layer tags, § Procedure markers, § Key RRC/NGAP/F1AP/E1AP messages)
- new YAML field / quirk → `config-format.md` (§ Sections, § Common overrides,
  § Field reference)
- failure signature / diagnostic step → `procedures/<proc>.md`
  (§ Investigation checklist or § Expected sequence)
- a new `procedures/<name>.md` → also add a row to `analysis-guide.md`
  § Investigating a failure; a new `scripts/<name>.py` → document it in
  `analysis-guide.md` and/or the procedure file
- a script bug → fix it in `scripts/*.py`

**For every edit**: propose the path + section + exact diff → confirm via
`AskUserQuestion` (**Apply** / **Edit wording** / **Skip**) → apply on approval →
for a `.py` change run `python3 -m py_compile` (re-run on the input when practical)
→ report what changed.

**Never** save run-specific values (RNTIs, UE IDs, AMF UE NGAP IDs, timestamps,
PCIs, gNB IDs, per-run narratives) — those don't generalise. Operator-/preference-
level knowledge goes to the project auto-memory under
`~/.claude/projects/<project-key>/memory/`, not `references/`.

**Maintenance trigger**: on "reorganize ocudu-gnb knowledge", re-read all of
`references/`, dedupe, fix stale grep patterns, and report a one-paragraph
summary — each edit under the confirm flow above.
