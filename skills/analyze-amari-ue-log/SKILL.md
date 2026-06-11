---
name: analyze-amari-ue-log
description: >
  Knowledge module for analyzing Amarisoft UE log files and run directories
  produced by Retina test runs — `ue.log` (the per-layer NAS/RRC/PHY/MAC trace),
  `stdout.log` (UE stats + CBR traffic), and `amarisoft_ue.cfg`. Provides the log
  format reference, per-procedure templates, grep recipes, and helper scripts.
  Invoked by a higher-level inspect/run orchestrator skill when it needs to
  analyze the UE-side log, or directly by a user to load UE-log analysis context
  (trigger phrases: "analyze
  this UE log", "look at the amarisoft log", or a path ending in `ue.log`,
  `amarisoft_ue.cfg`, or under `amarisoft-ue-*/`). It provides context and
  methodology; it does not drive an interactive analysis task — the calling agent
  does the work using this knowledge.
version: 0.1.0
user-invocable: true
allowed-tools: Bash(ls:*), Bash(grep:*), Bash(python3:*), Bash(find:*), Bash(file:*), Bash(stat:*), Bash(wc:*), Bash(head:*), Bash(tail:*), Bash(sort:*), Bash(realpath:*), Bash(sha256sum:*), Bash(cat:*), Edit, Write
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
- `references/scripts/` — pre-vetted helper scripts (`ue_log_summary.py`,
  `ue_log_search.py`) that emit compact summaries.
- `references/analysis-guide.md` — methodology for the three common activities
  (producing an overview, answering a targeted question, investigating a failure).

## How to use it

1. **Resolve the input** to a run directory (§ Step 1).
2. Follow `references/analysis-guide.md` for the activity at hand, leaning on the
   helper scripts and the format/procedure references.
3. Apply the § Efficiency rules throughout.
4. If analysis surfaces a generalisable learning, persist it per § Memory &
   self-maintenance.

---

## Step 1 — Input resolution

```bash
realpath <user-path>
ls -lh <user-path>
```

| Input | Resolution |
|---|---|
| Direct `ue.log` file | Run dir = parent directory |
| Directory containing `ue.log` directly | That directory is the run dir |
| `amarisoft-ue-N/` component dir | Find the latest `YYYY-MM-DD_HH-MM-SS/` subdirectory |
| Retina test dir `test_gnb[...]` | Look for `amarisoft-ue-*/` subdirectories |

**Multiple UE components in one test** (e.g. `amarisoft-ue-1`, `amarisoft-ue-2`):
the calling agent should scope to one UE component before invoking this
knowledge; if the target is unclear, it clarifies with the user.

**Run dir contents check:**

```bash
ls -lh <run-dir>
wc -l <run-dir>/ue.log
```

Bail with a clear message if `ue.log` is missing or 0 bytes.

---

## Step 2 — Follow the analysis guide

Load `references/analysis-guide.md` and follow the section that matches the
activity at hand — *Producing an overview*, *Answering a targeted question*, or
*Investigating a failure*. All three lean on the helper scripts in
`references/scripts/` and the procedure/format reference files in
`references/procedures/` and `references/log-format.md`.

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
- **Never** read raw `ue.log` into context — it can be 90k–200k+ lines.
  Always grep for specific patterns or use the summary script.
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

This skill improves itself over time. When analysis surfaces a generalisable
learning — or reveals that the skill's own docs or scripts are wrong — propose the
change and, **only after the user approves**, apply it with `Edit` (or `Write` for
a brand-new reference file).

**Only ever edit files inside this skill's own `references/` tree.** Never touch
files elsewhere in the repo, and never run git/commit — edits are left as diffs
for the user to review and commit.

Three kinds of edit:

1. **Add a learning** — put it where a reader would naturally look, matching the
   surrounding format (extend a table row, add a line to a code block, add a bullet
   to an existing list). **Do not prepend dates/timestamps.** Natural homes:
   - new grep recipe → `references/log-format.md` § Key grep recipes
   - new field / keyword / state / event → the matching table in
     `references/log-format.md` (§ Per-layer format, § NAS state values, § Key PHY
     channel keywords, § RRC channel keywords, § Key RRC message types,
     § PROD sim event types)
   - new failure signature / diagnostic step → the relevant
     `references/procedures/<proc>.md` (§ Investigation checklist or § Expected sequence)
   If a learning is substantial and distinct, create a **new file** following the
   template of its siblings and wire it in:
   - new `procedures/<name>.md` → add a row to the dispatch table in
     `references/analysis-guide.md` § Investigating a failure
   - new `scripts/<name>.py` → document its invocation in
     `references/analysis-guide.md` and/or the relevant procedure file
2. **Fix existing content** — correct a stale recipe, wrong field name, or
   outdated statement; dedupe/reorganise a reference file.
3. **Fix a helper script** — when analysis exposes a parsing or logic bug in
   `references/scripts/*.py`, correct it.

For every edit:
- **Propose first** — show the file path, the section, and the exact text/diff.
- **Confirm** via `AskUserQuestion`: **Apply** / **Edit wording** *(open text)* / **Skip**.
- **Apply** only on approval.
- **After editing a `.py` script**, run `python3 -m py_compile <script>` to confirm
  it still compiles (and, when practical, re-run it on the current input to confirm
  behaviour). If it breaks, fix or revert before finishing.
- **Report** what changed.

**Never** save specific RNTIs, UE IDs, timestamps, KPIs, or per-run root-cause
narratives — those do not generalise. Operator-/preference-level knowledge (user
shortcuts, local quirks, named conventions) goes to the project's auto-memory
directory under `~/.claude/projects/<project-key>/memory/`, not `references/`.

**Maintenance trigger**: if the user says "reorganize amari-ue knowledge", re-read
all files under `references/`, dedupe, fix stale grep patterns, and report a
one-paragraph summary of what changed — proposing each edit under the same confirm
flow above.
