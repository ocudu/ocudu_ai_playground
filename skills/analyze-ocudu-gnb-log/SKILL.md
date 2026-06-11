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
allowed-tools: Bash(ls:*), Bash(grep:*), Bash(python3:*), Bash(find:*), Bash(file:*), Bash(stat:*), Bash(wc:*), Bash(head:*), Bash(tail:*), Bash(sed:*), Bash(sort:*), Bash(comm:*), Bash(realpath:*), Bash(sha256sum:*), Bash(cat:*), Edit, Write
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
| Direct `gnb.log` file | Run dir = parent directory |
| Direct `ocudu_gnb.yml` / `stdout.log` | Run dir = parent directory |
| Directory containing `gnb.log` directly | That directory is the run dir |
| `ocudu-gnb-N-M/` component dir | Find the latest `YYYY-MM-DD_HH-MM-SS/` subdirectory containing `gnb.log` |
| Retina test dir `test_gnb[...]` | Look for `ocudu-gnb-*/` subdirectories — if more than one, the caller picks which |

**Multiple OCUDU components in one test** (e.g. `ocudu-gnb-1-1`, `ocudu-gnb-1-2`,
or a CU/DU split with `ocudu-cu-cp-*`, `ocudu-cu-up-*`, `ocudu-du-*`): the
calling agent should scope to one component before invoking this knowledge; if
the target is unclear, it clarifies with the user.

**Run dir contents check:**

```bash
ls -lh <run-dir>
wc -l <run-dir>/gnb.log
```

Bail with a clear message if `gnb.log` is missing or 0 bytes.

---

## Step 2 — Follow the analysis guide

Load `references/analysis-guide.md` and follow the section that matches the
activity at hand — *Producing an overview*, *Answering a targeted question*, or
*Investigating a failure*. All three lean on the helper scripts in
`references/scripts/`, the per-procedure files in `references/procedures/`, and
the format references `references/log-format.md` / `references/config-format.md`.

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
   - new layer / message / keyword → the matching table in
     `references/log-format.md` (§ Layer tags, § Procedure markers,
     § Key RRC/NGAP/F1AP/E1AP messages)
   - new YAML field / quirk → `references/config-format.md`
     (§ Sections, § Common overrides, § Field reference)
   - new failure signature / diagnostic step → the relevant
     `references/procedures/<proc>.md` (§ Investigation checklist or
     § Expected sequence)
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

**Never** save specific RNTIs, UE IDs, AMF UE NGAP IDs, run timestamps,
PCIs, gNB IDs, or per-run root-cause narratives — those do not generalise.
Operator-/preference-level knowledge (user shortcuts, local quirks, named
conventions) goes to the project's auto-memory directory under
`~/.claude/projects/<project-key>/memory/`, not `references/`.

**Maintenance trigger**: if the user says "reorganize ocudu-gnb knowledge",
re-read all files under `references/`, dedupe, fix stale grep patterns, and
report a one-paragraph summary of what changed — proposing each edit under the
same confirm flow above.
