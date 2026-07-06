# Loading the OCUDU source tree

The `reference/` docs here cover the **log-observable** layer. The code-side layer
beneath it — component architecture, threading model, why a metric is computed or a
procedure sequenced the way it is — lives in the **OCUDU source tree** (its markdown
docs, plus headers and source). This doc says when to reach for it, where to find
it, and how to read it.

## When

Escalation only. Reach for the source when the log-observable docs here don't
resolve a parameter/metric/sequence question — **when clues plateau, not before**.
Typical trigger: doubt about the exact meaning of a field in `metrics.json` / the
`gnb.log` trace that the format refs don't pin down.

## Where — preference order

If `$RAN_LOG_REFERENCE_OCUDU_PATH` is set, use that checkout — the user saved it in
a prior session. Otherwise, in order:

1. **In-project** (preferred) — a checkout vendored inside the current project as a
   git submodule or cloned directory. Check for it first (`.gitmodules`, or an
   `ocudu`/source directory in the project). Already permissioned — use it directly.
2. **Elsewhere under `$HOME`** — a separate checkout on the machine. Needs the
   user's explicit **choice + permission**: ask which path, confirm before relying
   on it. Do not assume a location.
3. **Public repo `https://gitlab.com/ocudu/ocudu`** — when no local checkout is
   usable. Needs the user's permission to fetch; shallow-clone into the session
   cache dir.

For tiers 2–3 the choice and permission are the user's to give — ask, don't assume.

Once a checkout is resolved by any tier, offer to persist its path as the
`RAN_LOG_REFERENCE_OCUDU_PATH` env var in project settings (`.claude/settings.json`
`env`) so future sessions reuse it without re-detecting or re-asking.

## Match the build

The run's build `commit`/`branch` in the `gnb.log` banner identifies the matching
source version — check out (or verify against) that revision so the code lines up
with the log under analysis.

Switching revisions is destructive, so guard it: if the checkout is **not**
in-project, or has **pending changes**, ask the user before dropping anything and
checking out a different branch. If they decline, either create a **temporary
worktree** at the target revision (leaving their tree untouched) or abort the
source-level analysis — don't switch anyway. An in-project checkout with a clean
tree can be checked out without asking.

## How to navigate

Start at the relevant subsystem directory's `README.md`, which indexes the sibling
`.md` docs beside it; follow what it points to. Not every subdirectory ships docs —
where a layer has none, fall back to its headers/source (`.h`/`.cpp`), or to the
`spec-explorer` skill for 3GPP behaviour (see `../common/spec-map.md`).

## Modifying the source

Reading is the default — don't edit the source tree to understand it. The one
exception: confirming a hypothesis that *requires* a source change (adding a unit
test, or a temporary log line). The **first time** this comes up in a session, ask
the user for authorization before touching anything, offering:

1. **Edit the `$RAN_LOG_REFERENCE_OCUDU_PATH` checkout in place** — modify their
   configured tree directly.
2. **Work in a throwaway git worktree** — isolate the change at the matching build
   revision, leaving their tree untouched.
3. **No authorization** — don't modify; fall back to reasoning from the read-only
   source, or leave the hypothesis unconfirmed.

Once granted, the choice holds for the rest of the session. Absent authorization,
the tree stays **read-only**.
