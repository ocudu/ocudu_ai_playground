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

- Explain to me succintly what the diff/change is about.
- Finds problems, code smells, etc.; do not fix them. It is also possible that the diff is fine and there are no issues.
- The CI jobs should be enough most of the time. Do not build or test locally without asking the user first, and only do it to confirm a hypothesis.
- Do not launch other code review skills and do not launch sub-agents without requesting the user first.

## Step 1 — Resolve and plan

```
${CLAUDE_SKILL_DIR}/scripts/resolve_diff.sh "<arguments>"
```

It resolves the target, fetches the base, sizes the diff without putting it in
context, and prints `KEY=value` lines followed by a `PLAN:` block covering
this diff specifically. Follow the PLAN, then Step 2. Run `--help` for the
accepted targets and keys.

Never trim the diff's context lines below the default three to save tokens:
reachability and real-time judgement need them.

## Step 2 — Review

Check every hunk against every checklist in [REFERENCE.md](REFERENCE.md),
judging it on its merits with enough surrounding context (`Read` the touched
files, `git log -p`/`git show` for a hunk's earlier revisions) — a hunk alone
often isn't enough to tell whether a pattern is safe. Skip stylistic nits that
match no checklist item; this is not a linter pass over what the compiler or
formatter already catches.

## Step 3 — Report findings

Merge and dedupe any subagent findings first, then call `ReportFindings` once
with the full list (empty if nothing survived), ranked most-severe-first —
that order *is* the severity signal: a memory-safety or untrusted-input bug,
or a new allocation/blocking call on a real-time path, outranks a correctness
nit, which outranks a convention or comment-style finding.

- `category` — kebab slug: `correctness`, `realtime-alloc`,
  `realtime-blocking`, `memory-safety`, `untrusted-input`.
- `failure_scenario` — required: the concrete inputs/state that lead to the
  wrong outcome. Convention and comment-style findings have none, so list them
  instead under a `### Conventions` heading, one `file:line — issue` per line.
- `verdict` — `CONFIRMED` when traced end to end, else `PLAUSIBLE`. Below
  plausible, don't report it.

Without `ReportFindings`: one markdown table, columns `File:Line`, `Type`,
`Severity`, `Summary`, same order, then a one-line note on what was reviewed
(files, diff range).
