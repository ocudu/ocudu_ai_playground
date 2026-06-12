---
name: analyze-amari-ue-log
description: >
  Knowledge module for analyzing Amarisoft UE logs — `ue.log`, `stdout.log`,
  `amarisoft_ue.cfg`: log-format ref, procedure templates, grep recipes, helper
  scripts. Use for such a run or an `amarisoft-ue-*/` dir, directly or via an
  inspect/run orchestrator. Provides context, not a task — the caller analyzes.
version: 0.1.0
user-invocable: true
allowed-tools: Bash(python3 *analyze-amari-ue-log/references*), Bash(ls:*), Bash(grep:*), Bash(find:*), Bash(file:*), Bash(stat:*), Bash(wc:*), Bash(head:*), Bash(tail:*), Bash(sort:*), Bash(realpath:*), Bash(sha256sum:*), Bash(cat:*), Edit, Write
---

# Analyze Amarisoft UE logs

Analyze Amarisoft UE diagnostic logs (`ue.log`), console output (`stdout.log`),
and configuration files (`amarisoft_ue.cfg`) produced by Retina test runs.
A single run directory typically contains:

| File | Description |
|---|---|
| `ue.log` | Detailed per-layer protocol trace (NAS/RRC/PHY/MAC/RLC/PDCP) |
| `stdout.log` | Console output: UE stats table, CBR traffic results, warnings |
| `amarisoft_ue.cfg` | JSON5 configuration: cell groups, UE list, sim events |
| `ps_info_lteue-avx2.txt` | Process CPU/memory snapshot (rarely needed) |

Ignore `metrics.json` — it is empty in these runs.

---

## What this skill provides

This is a **knowledge module**, not a task driver. It gives the calling agent
(usually a higher-level inspect/run orchestrator skill, sometimes a direct user
session) the context needed to analyze Amarisoft UE logs:

- `references/log-format.md` — the per-layer log layout and grep recipes.
- `references/procedures/` — per-procedure expected-sequence / failure-marker /
  investigation-checklist templates.
- `references/scripts/` — pre-vetted helper scripts (`resolve.py`,
  `ue_log_summary.py`, `ue_log_search.py`) that emit compact summaries.
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

It accepts a `ue.log` file, a run directory, an `amarisoft-ue-N/` component dir,
or a Retina `test_gnb[...]` dir, and resolves to the latest run directory holding
a `ue.log`. It prints the resolved run dir, the analysis artifacts present
(`ue.log`, `stdout.log`, `amarisoft_ue.cfg`), and a `verdict:` line; it exits
non-zero (`BAIL`) if no `ue.log` is found or it is empty. **Bail if the verdict is
not OK.** (UE logs are plain text — there is nothing to validate beyond presence,
so this is resolution + inventory, not a preflight.)

**Scope** — when a `test_gnb[...]` dir holds more than one UE component (e.g.
`amarisoft-ue-1` + `amarisoft-ue-2`), `resolve.py` reports them and notes which
one it resolved to; scope explicitly to the UE you mean before going further.

---

## Efficiency rules

- **Session cache dir.** Intermediate state (large grep spills, cached script
  outputs that the agent may want to post-filter later) lives under one
  per-session, user-private directory:
  `${CLAUDE_CODE_TMPDIR:-/tmp}/claude-skills-${CLAUDE_CODE_SESSION_ID}/`. It is
  shared with the `analyze-pcap` and `analyze-ocudu-gnb-log` skills so all
  three can cross-reference cached outputs in one run. Create the dir lazily (`mkdir -p` via the python
  helpers, or `python3 -c 'import os; os.makedirs(...)'`) and use the
  `amari-` prefix on files you write here (e.g. `amari-summary-<sha>.txt`,
  `amari-search-<sha>.txt`). The OS reaps `/tmp` on reboot — no manual
  cleanup needed.
- **Never** read raw `ue.log` into context — it can be more than 100k lines.
  Always grep for specific patterns or use a helper script.
- **Cap** any grep output at 200 lines with `| head -n 200`; for larger results
  write to `<cache-dir>/amari-<purpose>-<sha>.txt` and report the path.
- **Prefer** the helper scripts in `references/scripts/` over hand-crafted
  grep chains — they emit compact, token-efficient summaries.
- **Reuse** cached output: if a file you'd produce already exists in the cache
  dir for the same input, **post-filter** it (grep, head) instead of re-running
  the script.
- `stdout.log` is short (30–100 lines) — safe to read in full.
- `amarisoft_ue.cfg` is short (100–150 lines) — safe to read in full.
- In multi-UE mode (`ue_count > 1`), scope grep queries by UE ID early.

---

## Memory & self-maintenance

When analysis surfaces a generalisable learning — or reveals a doc/script is
wrong — propose the change and apply it **only after the user approves**, editing
**only files inside this skill's `references/` tree**. Never touch files
elsewhere, and never git/commit — edits are left as diffs.

**Where things go** (match the surrounding format; no dates/timestamps):
- new grep recipe → `log-format.md` § Key grep recipes
- new field / keyword / state / event → the matching table in `log-format.md`
  (§ Per-layer format, § NAS state values, § Key PHY channel keywords,
  § RRC channel keywords, § Key RRC message types, § PROD sim event types)
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

**Never** save run-specific values (RNTIs, UE IDs, timestamps, KPIs, per-run
narratives) — those don't generalise. Operator-/preference-level knowledge goes
to the project auto-memory under `~/.claude/projects/<project-key>/memory/`, not
`references/`.

**Maintenance trigger**: on "reorganize amari-ue knowledge", re-read all of
`references/`, dedupe, fix stale grep patterns, and report a one-paragraph
summary — each edit under the confirm flow above.
