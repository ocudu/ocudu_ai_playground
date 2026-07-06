---
name: ran-sherlog
description: >
  Analyze, summarize, query, or root-cause a whole OCUDU test/run directory that
  mixes artifacts from several components — an OCUDU app (gnb/du/cu/cu_cp/cu_up),
  an Amarisoft UE sim, an Amarisoft 5GC/MME, and packet captures. Triggers:
  "analyze/inspect this run", "why did this test fail", "did the UE's PRACH reach
  the gNB", "correlate the UE and gNB logs", a `test_gnb[...]` or
  `ocudu-*`/`amarisoft-*` directory, or a GitLab CI job URL. An ACTION skill: it
  drives an overview/query/investigation session, composing `ran-log-reference`,
  `spec-explorer`, and the OCUDU source to reach a conclusion.
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

- **GitLab CI job URL** → follow `references/ci-retrieval.md` to fetch + unzip the
  artifacts into a local directory, then continue as a local run.
- **A `test_gnb[...]` directory, a component dir, or a single run subdir** → use it.
- **Neither** → ask the user for a path or CI URL.

Then resolve + inventory the run through `ran-log-reference`: invoke it via the
`Skill` tool and follow its § Resolve & classify (a whole-run directory classifies
as `correlate`; its resolver prints the inventory and verdict — bail if not OK).
(`${RAN_LOG_REF_DIR}` in the commands below = `${CLAUDE_SKILL_DIR}/../ran-log-reference`,
the sibling skill dir — substitute it inline, since the shell doesn't persist env
vars between calls.)

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
subtree (`references/correlate/` — the master clock/slot/ID model and the
cross-artifact procedure traces; follow that subtree's own index). This skill keeps
only `references/ci-retrieval.md` and the three `mode-*.md` playbooks.

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
   does. `ran-log-reference` owns the loading protocol: read its
   `references/ocudu/source-code.md` and follow it — where to find a checkout
   (`$RAN_LOG_REFERENCE_OCUDU_PATH` env var → in-project → elsewhere under `$HOME`
   → public repo, with the permission model), matching the run's build, and
   read-only navigation.

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
- **Clocks/slots**: same-process logs+pcaps (and ZMQ/co-located UE↔gNB) share one
  clock (Δ≈0); off-host sources (VIAVI tester, remote 5GC, a UE sim on another
  box) may be offset — measure per run before comparing wall-clocks, and prefer
  the clock-independent **(SFN.slot, RNTI)** key. Details + the capinfos/tshark
  display-TZ trap: the clock model in `ran-log-reference`'s `correlate` subtree.
- In multi-UE runs, scope correlation by `--rnti` early; the cross-product of
  64 UEs × many slots is large.

---

## Memory & self-maintenance

The mechanics — what's worth persisting vs run-specific, the propose → confirm →
apply flow, one-way layering, never git-committing — live in `ran-log-reference`'s
self-maintenance; follow it. This skill only adds the routing between the two:

- A learning about **analysis** (any single- or cross-artifact detail) →
  `ran-log-reference` (its per-artifact subtree, or `references/correlate/` for
  correlation), routed per its self-maintenance.
- A learning about **running a session** (CI retrieval, a mode playbook, composing
  sources) → this skill's `references/` (`ci-retrieval.md`, `mode-*.md`).

**Maintenance trigger**: on "reorganize run-inspection knowledge", re-read this
skill's `references/`, dedupe, fix stale recipes, report — each edit under that
confirm flow.
