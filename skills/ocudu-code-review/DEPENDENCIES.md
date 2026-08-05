# OCUDU Code Review — `deps` mode

Checks the C++ tree for forbidden `#include` dependencies. Unlike the other
modes this one reads **files on disk**, not a diff, and runs two scripts rather
than applying a human checklist.

Two steps, always in this order: generate a dependency tree from the working
tree, then check that tree against the rules.

## Step 1 — Preconditions

**The working tree must be the code under review.** `git rev-parse HEAD` has to
equal the tip resolved in SKILL.md Step 1. If it doesn't, stop and tell the
user:

> `deps` mode analyses files on disk. Check out `<ref>` (or create a worktree
> with the `manage-worktree` skill) and re-run.

Do not analyse the working tree while reporting against a different ref: the
findings would name lines that aren't in the reviewed code.

**PyYAML must be importable.** Both scripts exit 2 with
`PyYAML required: pip install pyyaml` if it isn't.

**A `compile_commands.json` must exist.** The scripts use `build/` by default
and never guess another directory. On exit 2:

- If the error lists other build directories, **ask the user which to use**
  (their `compile_commands.json` mtimes are printed — a stale one has stale
  `-I` directories, so prefer a fresh one), then pass it via
  `--compile-commands <path>`. `--build=<dir>` on the mode's own invocation
  means the same thing.
- If no build directory has one, do **not** run `cmake` yourself. Print the
  command the error suggests (`cmake --preset default`, or
  `cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`) and stop. A configure
  mutates the user's build directory and can pick the wrong toolchain.

## Step 2 — Generate the tree

```
python3 ${CLAUDE_SKILL_DIR}/scripts/dependency/gen_dependency_tree.py
```

Run it from inside the C++ repo; it takes the repo root from `git rev-parse
--show-toplevel`. It scans every top-level directory holding sources (minus
`external/`, `build*/`, `cmake-build*/`) and writes
`<build-dir>/ocudu_dependency_tree.yml` — about 1.5 MB and ~2 s for OCUDU.

Always regenerate; never reuse an existing tree. It is cheap, and a stale tree
reports violations that no longer exist.

Relay a staleness warning about `compile_commands.json` if one appears: it
means `-I` directories may be missing, which inflates the unresolved count and
can hide real edges.

## Step 3 — Check the rules

```
python3 ${CLAUDE_SKILL_DIR}/scripts/dependency/check_dependency_rules.py --json
```

Add `--changed-files <paths…>` (or `--changed-files-from -` on stdin) **only**
when the review has a diff target. Get the list with:

```
git diff --name-only <base>...HEAD
```

With no target the mode is a full-tree audit: no `--changed-files`, every
violation reported.

The checker always evaluates the whole tree. `--changed-files` only splits the
report — matching violations become findings, the rest are counted as
pre-existing — and makes the exit code reflect the changed files alone.

Exit codes:

| Code | Meaning | What to do |
| --- | --- | --- |
| 0 | No violations in scope | Report clean, with the counts from the JSON |
| 1 | Violations found | Report them as findings |
| 2 | The ruleset or its inputs are broken | Fix the ruleset; **do not** report a clean review |

Exit 2 is never a code problem. It means a rule matches no files (usually a
rename left the rule dead), a duplicate `id`, an unknown key, or a missing
tree. Say which, and fix the rules file rather than working around it.

## Step 4 — Report

Each JSON finding becomes one `ReportFindings` entry:

| Field | Value |
| --- | --- |
| `file` | the finding's `file` (repo-relative, the including file) |
| `line` | the finding's `line` (the offending `#include`) |
| `category` | `forbidden-dependency` |
| `verdict` | `CONFIRMED` — a resolved include edge is a fact, not an inference |
| `summary` | `<rule_id>: <from> must not include <to>` |
| `failure_scenario` | the rule's `reason`, plus the chain for transitive findings |
| `short_summary` | `<rule_id>` plus the offending target's basename |

A forbidden dependency has no runtime failure scenario; state the
architectural consequence instead ("MAC can no longer be built or tested
without the DU manager"). Do not divert these to a `### Conventions` section —
they are machine-detected, file:line-anchored facts.

For a `transitive: true` finding, print the full `chain` in the finding text.
The `line` already points at the first edge — the only one the author of the
`from`-side file can change.

Also relay, in one line each:

- the pre-existing count, when `--changed-files` was used and
  `pre_existing_count` is non-zero: "N pre-existing violation(s) elsewhere,
  not caused by this diff";
- every entry in `warnings` (dead exemptions worth deleting);
- on a clean run, the counts: rules evaluated, files, edges, unresolved. A
  sudden jump in unresolved usually means a stale `compile_commands.json`.

## Step 5 — Interpreting a violation

Report the fact; leave the fix to the author. There are usually several, and
choosing between them needs design context this check doesn't have:

- forward-declare instead of including;
- move the shared type to a header both sides may include;
- invert the dependency behind an interface owned by the lower layer;
- if the dependency is genuinely correct, the **rule** is wrong — say so.

Never propose a rewrite unprompted; this skill finds problems.

## Adding a rule

Rules live in `scripts/dependency/ocudu_dependency_rules.yml`.

```yaml
version: 1
rules:
  - id: mac-must-not-depend-on-du
    from: "lib/mac/**"          # the including file
    to: "include/ocudu/du/**"   # the included file
    reason: >
      Why the dependency is wrong. Required — it becomes the finding's
      failure_scenario.
    transitive: false           # optional; true also flags indirect reach
    exempt:                     # optional; exact paths, no globs
      - from: lib/mac/foo.cpp
        to: include/ocudu/du/bar.h
        reason: "tracked in OCUDU-1234"
```

`from` and `to` each accept a string or a list of patterns. Globs are
repo-relative: `*` does not cross `/`, `**` does.

`to` may name trees that are never scanned for their own includes —
`external/**` for third-party code, `build/**` for generated headers. They
appear in the tree only as targets, which is enough for a rule like "no public
header may expose a third-party type".

The second kind covers constraints the `from`/`to` shape cannot express — that
two siblings must not see each other, without enumerating every pair:

```yaml
  - id: subsystem-private-headers-are-private
    kind: peer-isolation
    peers: "lib/*"
    reason: >
      Subsystems interact only through their public headers under include/ocudu/.
```

For every pair of distinct directories matching `peers`, files under one may
not include files under the other. `transitive` is not defined for this kind
and is rejected.

**The procedure for landing a rule:**

1. Write the rule.
2. Run the checker **full-tree** (no `--changed-files`).
3. Green → land it.
4. Red → either fix the violations first, or land the rule with an `exempt`
   entry per violation, each carrying an issue link in its `reason`.

Never land a red rule with no exemptions. A rule that is red on `main` makes
every later review noisy, and the noise is what gets the whole check switched
off.

The checker enforces the other half of this: a rule whose pattern matches no
files is an **error**, not a silent pass. Otherwise a rename would quietly turn
a rule into decoration that reports green forever.

## Running the scripts by hand

Both are standalone and repo-agnostic — any CMake project with a
`compile_commands.json` works. `--help` lists every flag. Useful ones:

- `--roots lib include` — scan a subset;
- `--rules <path>` — a different ruleset;
- `--repo <path>` — a project other than the cwd's;
- omit `--json` for human-readable output.

The tree itself is worth reading directly when a finding is surprising: it
records, per file, exactly what resolved and what didn't.
