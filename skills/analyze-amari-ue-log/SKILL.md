---
name: analyze-amari-ue-log
description: >
  Use this skill when the user asks to analyze, summarize, query, or investigate
  Amarisoft UE log files or run directories produced by Retina test runs.
  Trigger phrases include: "analyze this UE log", "look at the amarisoft log",
  "give me an overview of this UE run", "why did the UE fail to attach",
  "why did the handover fail", "debug this UE test", "investigate this UE failure",
  "what happened in this run", "root-cause this UE issue",
  or a path ending in `ue.log`, `amarisoft_ue.cfg`, `stdout.log`,
  or a path containing `amarisoft-ue-*/` or a retina test path
  like `retina/log/tests/*/test_gnb[...]`.
  The skill operates in three explicit modes — `overview`, `query`,
  `investigation` — and uses grep + python3 helper scripts to keep analysis
  cheap and token-efficient. When in doubt about scope or intent, the skill
  asks the user via AskUserQuestion rather than assuming.
version: 0.1.0
user-invocable: true
context: fork
allowed-tools: Bash(ls:*), Bash(grep:*), Bash(python3:*), Bash(find:*), Bash(file:*), Bash(stat:*), Bash(wc:*), Bash(head:*), Bash(tail:*), Bash(realpath:*), Bash(sha256sum:*), Bash(cat:*), Edit, Write
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

## Overall flow

1. **Input resolution** — resolve the user's path to a run directory.
2. **Mode dispatch** — pick `overview`, `query`, or `investigation`; ask if ambiguous.
3. **Mode branch** — load and follow `references/mode-{overview,query,investigation}.md`.
4. **Persist learnings** — after analysis, weave any generalisable findings into
   the natural place in `references/` (see § Memory & self-maintenance).

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
ask via `AskUserQuestion` which UE to focus on, unless the user already specified.

**Run dir contents check:**

```bash
ls -lh <run-dir>
wc -l <run-dir>/ue.log
```

Bail with a clear message if `ue.log` is missing or 0 bytes.

---

## Step 2 — Mode dispatch

| User wording | Mode |
|---|---|
| "overview", "summary", "what happened", "describe this run", no specific question | `overview` |
| explicit question ("why", "when", "how many", "did X happen", "which cell") | `query` |
| "investigate", "root cause", "debug", "why did this fail", "find the bug" | `investigation` |

When the user passes multiple instructions ("give me an overview then investigate
why the HO failed"), do them in order and ask before switching modes.

---

## Step 3 — Mode branch

Load and follow the matching file:

- `references/mode-overview.md`
- `references/mode-query.md`
- `references/mode-investigation.md`

All three modes share the helper scripts in `references/scripts/` and the
procedure/format reference files in `references/procedures/` and
`references/log-format.md`.

---

## Efficiency rules

- **Never** read raw `ue.log` into context — it can be 90k–200k+ lines.
  Always grep for specific patterns or use the summary script.
- **Cap** any grep output at 200 lines with `| head -n 200`; for larger results
  write to `/tmp/amari-ue-<sha256-of-path>.txt` and report the path.
- **Prefer** the helper scripts in `references/scripts/` over hand-crafted
  grep chains — they emit compact, token-efficient summaries.
- **Reuse** temp files: if `/tmp/amari-ue-<sha>.txt` exists for the same path,
  skip re-running the script.
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
     `references/mode-investigation.md` § Phase B
   - new `scripts/<name>.py` → document its invocation in the relevant `mode-*.md`
     and/or procedure file
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
