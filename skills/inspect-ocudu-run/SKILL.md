---
name: inspect-ocudu-run
description: >
  Use this skill when the user asks to analyze, summarize, query, or investigate
  a whole OCUDU test/run directory that mixes artifacts from several components
  — an OCUDU app (`gnb`/`du`/`cu`/`cu_cp`/`cu_up`), an Amarisoft UE simulator,
  an Amarisoft 5GC/MME, and packet captures. Trigger phrases include:
  "analyze this run", "inspect this test", "summarize this test directory",
  "what happened in this run", "why did this test fail", "root-cause this run",
  "did the UE's PRACH/PUSCH reach the gNB", "correlate the UE and gNB logs",
  "trace UE X end to end", a path to a `test_gnb[...]` directory or an
  `ocudu-*`/`amarisoft-*` component directory, or a GitLab CI job URL.
  This skill is an ORCHESTRATOR: it routes single-artifact analysis to the
  `analyze-ran-log` knowledge module (its `pcap` / `ocudu` / `amari-ue`
  type subtrees) via the Skill tool, and owns the cross-correlation of events
  across those sources (timestamp/slot alignment, UE-identity joining,
  PRACH/PUSCH/PUCCH sent-vs-received matching). When in doubt about scope or
  intent, it asks the user via AskUserQuestion rather than assuming.
version: 0.1.0
user-invocable: true
allowed-tools: Skill, Edit, Write, Bash(ls:*), Bash(grep:*), Bash(python3:*), Bash(find:*), Bash(file:*), Bash(stat:*), Bash(wc:*), Bash(head:*), Bash(tail:*), Bash(sed:*), Bash(sort:*), Bash(comm:*), Bash(realpath:*), Bash(sha256sum:*), Bash(cat:*), Bash(tshark:*), Bash(capinfos:*), Bash(curl:*), Bash(glab:*)
---

# Inspect an OCUDU run (orchestrator)

Analyze a complete OCUDU test/run directory by **orchestrating** the
`analyze-ran-log` per-type knowledge and **cross-correlating** the findings.
A Retina `test_gnb[...]` directory typically contains:

| Component dir | Artifacts | Analyzed with |
|---|---|---|
| `ocudu-gnb-*` / `ocudu-du-*` / `ocudu-cu-*` / `ocudu-cu-cp-*` / `ocudu-cu-up-*` | `gnb.log`/`du.log`/`cu*.log`, `stdout.log`, `ocudu_*.yml`, `metrics.json` | `analyze-ran-log` › `ocudu` |
| (the same dirs) | `*.pcap` (`ngap`/`f1ap`/`e1ap`/`mac`/`rlc`) | `analyze-ran-log` › `pcap` |
| `amarisoft-ue-*` | `ue.log`, `stdout.log`, `amarisoft_ue.cfg` | `analyze-ran-log` › `amari-ue` |
| `amarisoft-5gc-*` | `mme.log`, `amarisoft_mme.cfg` | light-touch here (future `amari-5gc` type) |
| (top level) | `testbed.json`, `test.html`, `agent-log-*.log` | this skill |

**Division of labor (core principle).** Single-artifact detail lives in the
`analyze-ran-log` type subtrees. **This skill's `references/` hold only
aggregation and
cross-correlation** material — how to line up the same event across the UE log,
the gNB log, and the pcaps. When analysis surfaces an artifact-specific learning,
propose it into the relevant **sub-skill**, not here (see § Memory).

---

## Overall flow

1. **Input resolution** — resolve the path to a run/test directory (or fetch a
   GitLab CI job first), then run the inventory.
2. **Mode dispatch** — pick `overview`, `query`, or `investigation`; ask if ambiguous.
3. **Mode branch** — load and follow `references/mode-{overview,query,investigation}.md`.
4. **Persist learnings** — route generalisable findings to the right skill (§ Memory).

---

## Step 1 — Input resolution

```bash
realpath <user-path>
```

- **GitLab CI job URL** → follow `references/ci-retrieval.md` to fetch + unzip the
  artifacts into a local directory, then continue as a local run.
- **A `test_gnb[...]` directory, a component dir, or a single run subdir** → use it.
- **Neither** → ask the user for a path or CI URL.

Then inventory the run (the dispatch backbone for every mode):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/run_inventory.py <path>
```

This lists the components present, each component's latest run subdir, the
artifacts found, the `testbed.json` component→IP map, the per-source clock
anchors, and which sub-skill owns each artifact. Bail clearly if no OCUDU
components are found.

If multiple OCUDU app components exist (e.g. split `ocudu-cu-cp-*` + `ocudu-du-*`,
or multiple gNBs), and the user's request doesn't pin one, ask via
`AskUserQuestion` which to focus on.

---

## Step 2 — Mode dispatch

| User wording | Mode |
|---|---|
| "overview", "summary", "what happened", "describe this run", no specific question | `overview` |
| explicit question ("why", "when", "how many", "did the UE's PRACH reach the gNB", "trace UE X") | `query` |
| "investigate", "root cause", "debug", "why did this fail", "find the bug" | `investigation` |

When the user passes multiple instructions, do them in order and ask before
switching modes.

---

## Step 3 — Mode branch

Load and follow the matching file:

- `references/mode-overview.md`
- `references/mode-query.md`
- `references/mode-investigation.md`

Shared references: `references/cross-correlation.md` (the master clock/slot/ID
model), `references/ue-identity-map.md`, `references/components.md`,
`references/ci-retrieval.md`, the cross-artifact traces in
`references/procedures/`, and the scripts in `scripts/`.

---

## Pulling in sub-skill knowledge (the Skill tool)

The per-artifact knowledge lives in the single `analyze-ran-log` skill — a
**knowledge module**, not a task runner. Invoke it **once** with the `Skill`
tool to load its shared methodology, then for each artifact read that artifact's
**type subtree** (`references/<type>/`) and run its helper scripts here yourself:

- OCUDU app logs / configs / metrics → `ocudu` type (`references/ocudu/`)
- Amarisoft UE log → `amari-ue` type (`references/amari-ue/`)
- `*.pcap` → `pcap` type (`references/pcap/`)
- Amarisoft 5GC `mme.log` → no type yet; do a light-touch grep here
  (registration / PDU-session / NGAP / `[E]` lines) and note the future
  `amari-5gc` hook.

Once `analyze-ran-log` is loaded, follow each type's
`references/<type>/analysis-guide.md` for the activity at hand and run its
summary/search scripts from that skill's `scripts/<type>/` dir, e.g.
`python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/pcap_overview.py` (pcap),
`scripts/ocudu/ocudu_log_summary.py` (gNB),
`scripts/amari-ue/ue_log_summary.py` (UE) — `${CLAUDE_SKILL_DIR}` resolves to the
`analyze-ran-log` directory while its guidance is active. This skill's own
`allowed-tools` already include `tshark`, `capinfos`, and `python3`, so the
per-artifact scripts run here directly.

**Do the cross-correlation yourself** — that is this skill's job and its scripts
read the raw artifacts directly:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/align_clocks.py <run-dir>
python3 ${CLAUDE_SKILL_DIR}/scripts/correlate_radio.py <run-dir> --kind pusch
python3 ${CLAUDE_SKILL_DIR}/scripts/map_ue_ids.py <ngap|f1ap|e1ap>.pcap
```

---

## Efficiency rules

- **Session cache dir.** Intermediate state lives under the per-session,
  user-private directory shared by all four skills:
  `${CLAUDE_CODE_TMPDIR:-/tmp}/claude-skills-${CLAUDE_CODE_SESSION_ID}/`. Write
  this skill's spills with the **`run-`** prefix (the helper scripts do this via
  `utils.cache_path`). **Reuse** the sub-skills' cached outputs when present
  (`ocudu-`, `amari-`, `pcap-`) instead of recomputing. The OS reaps `/tmp` on
  reboot.
- **Never** read raw `gnb.log` / `ue.log` / pcaps into context — use the
  sub-skills' summary/search scripts (which emit compact summaries) and the
  correlation scripts (which emit compact tables). Cap any ad-hoc grep at 200 lines.
- **Clocks/slots**: all logs and pcap `frame.time_epoch` share **UTC**; never
  compare a `capinfos`/`tshark` human time (local-TZ display) to a log string —
  use raw `frame.time_epoch`. The exact cross-source radio key is
  **(SFN.slot, RNTI)** at the PHY layer. See `references/cross-correlation.md`.
- In multi-UE runs, scope correlation by `--rnti` early; the cross-product of
  64 UEs × many slots is large.

---

## Memory & self-maintenance

This skill and the `analyze-ran-log` module improve over time. When analysis
surfaces a generalisable learning — or reveals a doc/script is wrong — propose
the change and, **only after the user approves**, apply it with `Edit`/`Write`.

**Routing rule (important):**
- A learning that is specific to **one artifact type** (a gNB log field, a UE log
  pattern, a pcap dissector quirk) → propose it into that type's subtree in
  `analyze-ran-log` (`references/ocudu/`, `references/amari-ue/`,
  `references/pcap/`). This skill may write there on approval, per the user's
  intent.
- A learning about **cross-correlation** (clock/slot alignment, identifier
  joining, a multi-source procedure trace) → keep it in **this** skill's
  `references/`; a correlation-script fix goes in **this** skill's `scripts/`.

For every edit: **propose first** (path, section, exact diff) → **confirm** via
`AskUserQuestion` (**Apply** / **Edit wording** *(open)* / **Skip**) → **apply**
on approval → **report**. After editing a `.py` script, run
`python3 -m py_compile <script>` (and re-run it on the current input when
practical). Never run git/commit — edits are left as diffs.

**Never** save run-specific values (RNTIs, UE-IDs, frame numbers, timestamps,
PCIs, per-run root-cause narratives). Operator-/preference-level knowledge goes
to the project auto-memory under `~/.claude/projects/<project-key>/memory/`.

**Maintenance trigger**: if the user says "reorganize run-inspection knowledge",
re-read all files under this skill's `references/`, dedupe, fix stale recipes,
and report a one-paragraph summary — proposing each edit under the confirm flow.
