---
name: ocudu-code-review
description: >
  Review OCUDU changes for correctness, OCUDU C++ conventions, real-time-path
  safety and security. Use when asked to review OCUDU code, a diff, a branch
  or a GitLab MR. Trigger phrases: "review this OCUDU change", "code review
  this branch/diff/MR", "check this for RT-path safety", "security review this
  OCUDU code", "/ocudu-code-review".
argument-hint: [target] [--base=<ref>] [--fanout]
arguments: [target]
version: 0.1.0
user-invocable: true
context: inline
license: BSD-3-Clause-Open-MPI
compatibility: >
  Requires git, plus network access to `origin` for the base fetch. A GitLab
  MR URL resolves through `origin` (`refs/merge-requests/<iid>/head`), so
  `origin` must point at the same gitlab.com/ocudu project as the MR. An
  authenticated `glab` is optional: with it, an MR is compared against its
  real target branch and its existing review threads are digested so the
  review doesn't repeat them; without it, against `origin/dev` and blind to
  the threads.
allowed-tools: Bash(*ocudu-code-review/scripts/resolve_diff.sh*), Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git rev-parse:*), Bash(git branch:*), Read, Grep, Glob, Agent, ReportFindings
---

# OCUDU Code Review

**Usage:** `/ocudu-code-review [target] [--base=<ref>] [--fanout]`

Defaults: `target` = current branch, `--base` = the MR's target branch else
`origin/dev`. Anything in the argument string that isn't a flag is the
`target`. `--fanout` reviews a large diff through subagents.

## Guidelines

- Summarize the change succinctly.
- Find problems; do not fix them. No findings is a valid outcome.
- Do not build or test locally without asking the user first; rely on CI.
- Do not launch other code review skills, or subagents beyond what the PLAN
  says, without asking the user first.

## Step 1 — Resolve and plan

```
${CLAUDE_SKILL_DIR}/scripts/resolve_diff.sh "<arguments>"
```

It prints `KEY=value` lines and a `PLAN:` block. Follow the PLAN, then Step 2.
`--help` lists accepted targets and keys.

Never trim diff context below the default three lines.

## Step 2 — Review

Check every hunk against every checklist in [REFERENCE.md](REFERENCE.md). Skip stylistic nits
that match no checklist item.

## Step 3 — Report findings

Merge and dedupe any subagent findings first, then call `ReportFindings` once
with the full list, ranked most-severe-first: memory-safety, untrusted-input
and real-time findings, then correctness, then conventions and comment style.

- `category` — kebab slug: `correctness`, `realtime-alloc`,
  `realtime-blocking`, `memory-safety`, `untrusted-input`.
- `failure_scenario` — required: the concrete inputs/state that lead to the
  wrong outcome. List convention and comment-style findings instead under a
  `### Conventions` heading, one `file:line — issue` per line.
- `verdict` — `CONFIRMED` when traced end to end, else `PLAUSIBLE`. Drop
  anything weaker.

Without `ReportFindings`: one markdown table, columns `File:Line`, `Type`,
`Severity`, `Summary`, same order, then a one-line note on what was reviewed
(files, diff range).
