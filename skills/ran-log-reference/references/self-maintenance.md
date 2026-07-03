# Updating this skill (references & scripts)

Load this **only** when an analysis session has actually surfaced something to
persist — a generalisable learning, or a doc/script that is wrong or stale. For
ordinary analysis it is not needed.

## Scope (hard limits)

- Edit **only** files inside this skill's own `references/<type>/` and
  `scripts/<type>/` trees (`ocudu`, `amari-ue`, `pcap`, `viavi`, `correlate`),
  the shared `references/common/` subtree, plus the shared `references/*.md`.
- **Never** touch files elsewhere in the repo or the user's project.
- **Never** `git add`/`commit`/`push` — leave edits as working-tree diffs for the
  user to review.

## Step 1 — decide whether it belongs here at all

Before editing, classify what you learned:

1. **Is it general, or just this run's verdict?** Only write reusable guidance —
   *candidate causes and how to attribute them*, mechanisms, and the observable
   log signal to measure each. Do **not** write the conclusion from the specific
   log under analysis (e.g. "X dominated", "the bottleneck was Y here"). Frame it
   as "this latency/behaviour can come from A/B/C — check signal Z to tell which".
2. **Does it depend on log lines that exist only on a work branch?** If a
   parser/profiler keys on trace points not yet merged to mainline, keep that
   tooling in a **temp script** (e.g. under `/tmp`), not in `scripts/<type>/`.
   Fold it into the skill only once the corresponding log lines are mainlined.
   General *knowledge* about the mechanism can still be written here, phrased
   against mainline-observable signals.
3. **Is it operator/preference knowledge** (how the user likes to work, a
   workflow correction)? That goes to the project auto-memory under
   `~/.claude/projects/<project-key>/memory/`, **not** here.
4. **Is it run-specific data?** RNTIs, UE-IDs, AMF UE NGAP IDs, frame/slot
   numbers, timestamps, PCIs, KPIs, per-run narratives — **never** persist these.
   Code-derived constants (fixed slot windows, timeout values, message names) are
   fine because they generalise.

If none of 1–2 apply (it's not generalisable, or it's preference/run-specific),
do not edit the skill.

## Step 2 — where it goes

- **Single-artifact learning** → the routing table in
  `references/<type>/conventions.md` (§ Memory routing) names the exact file and
  section for a new grep/tshark recipe, log marker, config field, failure
  signature, etc. Observation-surface detail (a log line, a tshark filter, a UE
  marker) stays in the type subtree even if it observes a shared procedure.
- **Artifact-agnostic learning** (protocol/procedure *semantics* shared across
  types, an identifier definition, a 3GPP spec pointer, a FAPI message) →
  `references/common/` (`protocols/<proto>.md`, `procedures/<name>.md`,
  `identifiers.md`, `spec-map.md`, `fapi.md`). If a per-type doc restates it, thin
  that doc to link here.
- **Cross-artifact learning** (clock/slot alignment, identifier joining, a
  multi-source procedure trace) → `references/correlate/`
  (`cross-correlation.md`, `ue-identity-map.md`, or `correlate/procedures/*.md`);
  a correlation-script fix → `scripts/correlate/`.
- **Script bug/feature** → the matching `scripts/<type>/*.py`.

### Layering — the dependency direction is one-way

The subtrees form layers; a doc may link **down** (to a more general layer) but
**never up**:

```
common/            (base: artifact-agnostic semantics, spec, FAPI, identifiers)
   ▲
per-type subtrees  (ocudu / pcap / amari-ue / viavi — observation of common)
   ▲
correlate/         (composes per-type observations)
```

- A `references/common/` doc must **not** reference `ocudu` / `pcap` / `amari-ue`
  / `viavi` / `correlate` (no `../../<type>/…` or `../correlate/…` paths). It may
  *name* an artifact kind descriptively (e.g. a "where seen" column: "pcap `f1ap`
  (11)", "gNB log (SCHED)") — that is not a folder link. Keep it self-contained;
  link only to sibling `common/` docs.
- A per-type doc **may** link into `common/` (the reverse direction — this is how
  an observation cites its semantics/ladder), but not into a sibling per-type
  subtree.
- `correlate/` may link into both `common/` and the per-type subtrees it joins.

When adding to `common/`, the observation mapping lives on the artifact side: the
per-type doc links up to the common ladder, not the other way round.

## Step 3 — apply (confirm flow)

For every edit:

1. Propose the **path + section + exact diff**.
2. Confirm via `AskUserQuestion` (**Apply** / **Edit wording** / **Skip**) — unless
   the user has already explicitly told you to make the change.
3. Apply on approval.
4. For a `.py` change, run `python3 -m py_compile` (and re-run it on the input
   when practical).
5. Report what changed.

## Maintenance trigger

On "reorganize <type> knowledge" (e.g. "reorganize pcap knowledge"): re-read all
of `references/<type>/`, dedupe, fix stale tshark/grep syntax and dead pointers,
and report a one-paragraph summary — each edit under the confirm flow above.
