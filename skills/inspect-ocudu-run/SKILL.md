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
  This is an ACTION skill: it drives an overview/query/investigation session and
  composes knowledge sources — the `ran-log-reference` module (per-artifact +
  cross-artifact `correlate`), the `spec-explorer` skill for expected 3GPP
  behavior, and the OCUDU source — to reach a conclusion. When in doubt about
  scope or intent, it asks the user via AskUserQuestion rather than assuming.
version: 0.1.0
user-invocable: true
allowed-tools: Skill, Edit, Write, Bash(ls:*), Bash(grep:*), Bash(python3:*), Bash(find:*), Bash(file:*), Bash(stat:*), Bash(wc:*), Bash(head:*), Bash(tail:*), Bash(sed:*), Bash(sort:*), Bash(comm:*), Bash(realpath:*), Bash(sha256sum:*), Bash(cat:*), Bash(tshark:*), Bash(capinfos:*), Bash(curl:*), Bash(glab:*), Bash(git:*)
---

# Inspect an OCUDU run (action skill)

Drive the analysis of a complete OCUDU test/run directory: resolve/fetch the run,
pick a mode, and **compose knowledge sources** to reach a conclusion. The
per-artifact and cross-artifact analysis *knowledge* lives in the
`ran-log-reference` module; this skill orchestrates a session around it and can
also consult the 3GPP specs and the OCUDU source. A Retina `test_gnb[...]`
directory typically contains:

| Component dir | Artifacts | Analyzed with |
|---|---|---|
| `ocudu-gnb-*` / `ocudu-du-*` / `ocudu-cu-*` / `ocudu-cu-cp-*` / `ocudu-cu-up-*` | `gnb.log`/`du.log`/`cu*.log`, `stdout.log`, `ocudu_*.yml`, `metrics.json` | `ran-log-reference` › `ocudu` |
| (the same dirs) | `*.pcap` (`ngap`/`f1ap`/`e1ap`/`mac`/`rlc`) | `ran-log-reference` › `pcap` |
| `amarisoft-ue-*` | `ue.log`, `stdout.log`, `amarisoft_ue.cfg` | `ran-log-reference` › `amari-ue` |
| `amarisoft-5gc-*` | `mme.log`, `amarisoft_mme.cfg` | light-touch here (future `amari-5gc` type) |
| (whole run, ≥2 components) | cross-artifact correlation | `ran-log-reference` › `correlate` |
| (top level) | `testbed.json`, `test.html`, `agent-log-*.log` | this skill |

**Division of labor (core principle).** All analysis *knowledge* — per-artifact
**and** cross-artifact correlation — lives in `ran-log-reference` (the `correlate`
subtree owns clock/slot alignment, UE-identity joining, sent-vs-received
matching). **This skill holds only *action* material**: how to fetch a run, how
to run an overview/query/investigation session, and how to weave in extra sources.
When analysis surfaces an analysis learning, route it into `ran-log-reference`,
not here (see § Memory).

---

## Overall flow

1. **Input resolution** — resolve the path to a run/test directory (or fetch a
   GitLab CI job first), then resolve + inventory it via `ran-log-reference`.
2. **Mode dispatch** — pick `overview`, `query`, or `investigation`; ask if ambiguous.
3. **Mode branch** — load and follow `references/mode-{overview,query,investigation}.md`.
4. **Persist learnings** — route generalisable findings to the right place (§ Memory).

---

## Step 1 — Input resolution

```bash
realpath <user-path>
```

- **GitLab CI job URL** → follow `references/ci-retrieval.md` to fetch + unzip the
  artifacts into a local directory, then continue as a local run.
- **A `test_gnb[...]` directory, a component dir, or a single run subdir** → use it.
- **Neither** → ask the user for a path or CI URL.

Then load the knowledge module and resolve the run through it. Invoke
`ran-log-reference` via the `Skill` tool, then:

```bash
python3 ${RAN_LOG_REF_DIR}/scripts/resolve.py <path>
```

A whole-run directory classifies as **`correlate`** and its delegate prints the
inventory — components present, each component's latest run subdir, the artifacts
found, the `testbed.json` component→IP map, the per-source clock anchors, and which
`ran-log-reference` type analyses each. Bail clearly if no OCUDU components are found.
(`${RAN_LOG_REF_DIR}` = that skill's directory, i.e. `${CLAUDE_SKILL_DIR}`
while its guidance is active.)

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

The analysis knowledge those modes lean on lives in `ran-log-reference`: the
per-artifact subtrees (`references/{pcap,ocudu,amari-ue}/`) and the **`correlate`**
subtree (`references/correlate/` — the master clock/slot/ID model in
`cross-correlation.md`, `ue-identity-map.md`, `components.md`, and the
cross-artifact traces in `correlate/procedures/`). This skill keeps only
`references/ci-retrieval.md` and the three `mode-*.md` playbooks.

---

## Composing sources

Drive the session by pulling on whatever sources the task needs. Invoke each
knowledge skill **once** with the `Skill` tool, then run its scripts / read its
references here yourself.

1. **`ran-log-reference`** — the primary source. Per-artifact: follow each type's
   `references/<type>/analysis-guide.md` and run its scripts, e.g.
   `python3 ${RAN_LOG_REF_DIR}/scripts/pcap/pcap_overview.py`,
   `scripts/ocudu/ocudu_log_summary.py`, `scripts/amari-ue/ue_log_summary.py`.
   Cross-artifact: read `references/correlate/` and run its scripts:
   ```bash
   python3 ${RAN_LOG_REF_DIR}/scripts/correlate/resolve.py <run-dir>
   python3 ${RAN_LOG_REF_DIR}/scripts/correlate/align_clocks.py <run-dir>
   python3 ${RAN_LOG_REF_DIR}/scripts/correlate/correlate_radio.py <run-dir> --kind pusch
   python3 ${RAN_LOG_REF_DIR}/scripts/correlate/map_ue_ids.py <ngap|f1ap|e1ap>.pcap
   ```
2. **`spec-explorer`** — when a finding needs the *expected* 3GPP behavior
   (procedure sequence, IE meaning, timer): invoke it to get canonical,
   line-numbered spec text rather than reasoning from memory.
3. **OCUDU source** — when behavior depends on what the implementation actually
   does: use a local checkout if one is available (path is environment-specific,
   e.g. `~/srs/ocudu` — confirm before relying on it); otherwise fetch it from
   `https://gitlab.com/ocudu/ocudu` (clone shallow into the session cache dir).

This skill's `allowed-tools` already include `Skill`, `python3`, `tshark`,
`capinfos`, `git`, so the above run here directly.

---

## Efficiency rules

- **Session cache dir.** Intermediate state lives under the per-session,
  user-private directory shared with `ran-log-reference`:
  `${CLAUDE_CODE_TMPDIR:-/tmp}/claude-skills-${CLAUDE_CODE_SESSION_ID}/`. **Reuse**
  `ran-log-reference`'s cached outputs when present (`pcap-`, `ocudu-`, `amari-`,
  `correlate-`) instead of recomputing. The OS reaps `/tmp` on reboot.
- **Never** read raw `gnb.log` / `ue.log` / pcaps into context — use
  `ran-log-reference`'s summary/search and correlate scripts (compact output). Cap
  any ad-hoc grep at 200 lines.
- **Clocks/slots**: a component and the pcaps it writes share one clock by
  construction (same process — `gnb.log` ↔ `gnb_*.pcap` Δ≈0). But don't assume it
  across processes/hosts: an off-host source (VIAVI tester, remote 5GC, a UE sim
  on another box) can be offset by seconds to hours — measure the offset per run
  before comparing wall-clocks. Prefer the clock-independent key
  **(SFN.slot, RNTI)** at the PHY layer (and RNTI/TC-RNTI chains). Separately,
  never compare a `capinfos`/`tshark` human time (local-TZ display) to a log
  string — use raw `frame.time_epoch`. See `ran-log-reference` ›
  `references/correlate/cross-correlation.md`.
- In multi-UE runs, scope correlation by `--rnti` early; the cross-product of
  64 UEs × many slots is large.

---

## Memory & self-maintenance

This skill and the `ran-log-reference` module improve over time. When analysis
surfaces a generalisable learning — or reveals a doc/script is wrong — propose
the change and, **only after the user approves**, apply it with `Edit`/`Write`.

**Routing rule (important):**
- A learning about **analysis** — whether a single-artifact detail (a gNB log
  field, a pcap dissector quirk) **or** a cross-artifact one (clock/slot
  alignment, identifier joining, a multi-source procedure trace) → propose it into
  `ran-log-reference`: the per-artifact subtree, or `references/correlate/` /
  `scripts/correlate/` for correlation. This skill may write there on approval.
- A learning about **running a session** (CI retrieval, mode playbook, composing
  sources) → keep it in **this** skill's `references/` (`ci-retrieval.md`,
  `mode-*.md`).

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
