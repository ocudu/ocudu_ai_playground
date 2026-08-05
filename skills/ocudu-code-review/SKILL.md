---
name: ocudu-code-review
description: >
  Review OCUDU C++ changes (gnb/du/cu) for correctness, style, real-time-path
  safety, security, and forbidden include dependencies. Runs one or more
  selectable modes: general, realtime, security, all (default), or deps
  (opt-in). Use when asked to review OCUDU code, a diff, a branch, or a GitLab
  MR against OCUDU conventions. Trigger phrases: "review this OCUDU change",
  "code review this branch/diff/MR", "check this for RT-path safety", "security
  review this OCUDU code", "check for bad/forbidden include dependencies",
  "check the layering", "/ocudu-code-review".
argument-hint: [target] [--mode=general|realtime|security|all|deps] [--base=<ref>] [--build=<dir>]
arguments: [target]
version: 0.1.0
user-invocable: true
context: inline
license: BSD-3-Clause-Open-MPI
compatibility: >
  Requires git. Branch/MR reviews diff against a remote base (default
  `origin/main`), fetched fresh, so they need network access to `origin`.
  Reviewing a GitLab MR URL fetches the MR's head ref directly from `origin`
  (`refs/merge-requests/<iid>/head`) — no GitLab API token needed, but
  `origin` must point at the same gitlab.com/ocudu project as the MR. The
  `deps` mode additionally requires PyYAML (`pip install pyyaml`), the reviewed
  code checked out in the working tree, and a `compile_commands.json` in the
  C++ repo (`cmake --preset default`, or `cmake -B build
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`).
allowed-tools: Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git fetch:*), Bash(git merge-base:*), Bash(git rev-parse:*), Bash(git branch:*), Bash(*ocudu-code-review/scripts/resolve_mr_ref.sh*), Bash(python3 *ocudu-code-review/scripts/dependency/*), Read, Grep, Glob, ReportFindings
---

# OCUDU Code Review

**Usage:** `/ocudu-code-review [target] [--mode=general|realtime|security|all|deps] [--base=<ref>] [--build=<dir>]`

- `target` (optional): a git ref (branch or commit), a range (`main..feature`),
  `working`/`staged` for uncommitted work, or a GitLab MR URL under
  `gitlab.com/ocudu`. Default: the current branch, reviewed as a whole against
  the base.
- `--base` (optional, default `origin/main`): the ref a branch/MR is reviewed
  against. Defaults to *remote* main so a review matches what a reviewer sees
  on the MR/PR, not a possibly-stale local `main`. Override for a different
  target branch, e.g. `--base=origin/release`.
- `--mode` (optional, default `all`): which checklist(s) in
  [REFERENCE.md](REFERENCE.md) to apply.
  - `general` — correctness/logic bugs and OCUDU C++ conventions (member
    ordering, error handling, comment style).
  - `realtime` — allocation/blocking-call safety on hot, latency-sensitive
    paths.
  - `security` — memory safety and untrusted-input handling.
  - `all` — every mode above.
  - `deps` — forbidden `#include` dependencies, checked by script against
    [DEPENDENCIES.md](DEPENDENCIES.md)'s rule file. **Opt-in: not part of
    `all`**, because it needs the reviewed code checked out and a
    `compile_commands.json`, neither of which a default review can assume.
- `--build` (optional, `deps` mode only): the build directory whose
  `compile_commands.json` to use, when it isn't `build/`.

This skill finds problems; it does not fix them or propose refactors. For
cleanup/simplification of already-correct code, point the user at the
`simplify` skill instead.

## Step 1 — Resolve the diff

Branch and MR reviews compare a **base** against a **tip** with three dots
(`base...tip` — merge-base diff, so only the tip's own commits show, not
commits that landed on the base meanwhile). The base is `--base` (default
`origin/main`). Fetch it fresh before diffing so a stale local ref doesn't
produce phantom findings: `git fetch --quiet origin <base-branch>` (for the
`origin/main` default, `git fetch --quiet origin main`; skip the fetch only
if the base is a purely local ref).

Pick the tip from `target`:

- **No target**: tip = `HEAD` — reviews the current branch as a whole against
  the base: `git diff origin/main...HEAD`. If the working tree is dirty and
  the user likely means their uncommitted work instead, say so and offer the
  `working`/`staged` targets below.
- **`working`**: uncommitted changes, staged and unstaged — `git diff HEAD`
  (local-only; no base fetch).
- **`staged`**: staged changes only — `git diff --staged` (local-only).
- **A branch or commit ref**: tip = that ref — `git diff origin/main...<ref>`.
  To review a single commit in isolation instead, pass its range explicitly,
  e.g. `abc123^..abc123`, or use `git show abc123`.
- **A range** (`A..B` or `A...B`): pass it straight through to `git diff`
  unchanged — the user chose the exact endpoints.
- **A GitLab MR URL** (`.../-/merge_requests/<iid>`): run
  `${CLAUDE_SKILL_DIR}/scripts/resolve_mr_ref.sh <url>`; it fetches the MR head
  into a local ref and prints it. That printed ref is the tip:
  `git diff origin/main...<printed-ref>`. Without a GitLab token this skill
  can't read the MR's real target branch; if it targets something other than
  `main`, pass the right base with `--base=` (or ask the user).

If the resolved diff is empty, report "No changes to review" and stop.

Exception for `deps` mode with no `target`: it needs no diff at all and audits
the whole working tree, so skip this step entirely when `deps` is the only
active mode and no target was given.

Read the full diff, plus enough surrounding context (`Read` on the touched
files, `git log -p`/`git show` for prior revisions of a hunk when intent is
unclear) to judge each change on its merits — a diff hunk alone often isn't
enough to tell whether a pattern is safe.

## Step 2 — Determine mode(s)

Arguments arrive as one string. Everything in it that isn't a `--mode=`,
`--base=` or `--build=` flag is the `target` from Step 1; the optional
`--mode=` flag picks the checklist(s):

- no flag, or `--mode=all` — apply every section **except** `deps`.
- `--mode=general` / `--mode=realtime` / `--mode=security` — that one section.
- `--mode=deps` — the dependency check only.
- comma-separate to combine, e.g. `--mode=realtime,security` or
  `--mode=all,deps`.

Load only the matching checklist section(s) from [REFERENCE.md](REFERENCE.md).
`deps` has no section there — it follows [DEPENDENCIES.md](DEPENDENCIES.md)
instead.

## Step 3 — Review

Walk the diff file by file, hunk by hunk. For each hunk, check it against
every checklist item in the active mode(s). Judge real-time-path status and
untrusted-input status by tracing callers/context, not by filename guesses —
see the "Determining reachability" notes in REFERENCE.md before flagging
anything in `realtime` or `security` mode.

Skip stylistic nits that don't match a concrete checklist item — this skill
is not a linter pass over things the compiler or formatter already catches.

`deps` mode does not walk the diff. Follow [DEPENDENCIES.md](DEPENDENCIES.md)
from its Step 1 instead, then report through Step 4 below as it describes. When
`deps` runs alongside other modes, do the hunk walk for those modes and the
script run for `deps`, and report the findings together.

## Step 4 — Report findings

Prefer the `ReportFindings` tool when it's available — it feeds the host's
review UI. It has **no** severity or mode field, so encode those as follows,
and call it once with the full list (empty list if nothing survived review):

- **Rank** findings most-severe-first in the array — that ordering *is* the
  severity signal (see below).
- Put the finding type in `category` as a kebab-case slug, e.g.
  `correctness`, `realtime-alloc`, `realtime-blocking`, `memory-safety`,
  `untrusted-input`, `forbidden-dependency`.
- `failure_scenario` is required: give the concrete inputs/state that lead to
  the wrong outcome. Convention and comment-style findings have no runtime
  failure scenario — don't force them through `ReportFindings`; list them
  separately (below). `forbidden-dependency` findings are the exception: they
  have no runtime scenario either, but they are machine-detected and
  line-anchored, so they do go through `ReportFindings` with the architectural
  consequence as the scenario.
- Set `verdict: CONFIRMED` for a finding you traced end to end, `PLAUSIBLE`
  for one you couldn't fully confirm (e.g. reachability uncertain — see
  REFERENCE.md). Don't report a finding you can't at least make plausible.

List convention/comment-style findings (anything with no failure scenario)
under a `### Conventions` heading, one line each as `file:line — issue`.

If `ReportFindings` is **not** available, print everything as one markdown
table: columns `File:Line`, `Type`, `Severity`, `Summary`, ordered
most-severe first. End with a one-line note on what was reviewed (files,
mode(s), diff range).

**Severity ordering** (drives array order and the Severity column): a
memory-safety or untrusted-input bug, or a newly introduced allocation/
blocking call on a real-time path, outranks a correctness nit, which outranks
a forbidden dependency, which outranks a convention/comment-style finding.
