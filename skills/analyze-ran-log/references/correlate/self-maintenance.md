# Updating the `correlate` subtree

Routing table for cross-artifact learnings. The shared rules — what is/isn't worth
persisting, the confirm-before-edit flow, the one-way layering — live in
`../self-maintenance.md`; **read that first**. This file only says where a
`correlate` learning lands.

## Where it goes

| Learning | File |
|---|---|
| A clock/timestamp fact, a matching-key rule, an SFN-wrap or slot-lag caveat, a display-TZ trap | `cross-correlation.md` (the master model) |
| A UE identifier, how two sources' IDs chain, an ID-recycling caveat, a new join recipe between components | `ue-identity-map.md` |
| Run-directory layout, a component naming pattern, a `testbed.json` detail, which type analyses an artifact | `components.md` |
| A new multi-source procedure trace, or a hop added to an existing one | `procedures/<name>.md` |
| A cross-source anomaly worth surfacing in every overview | `overview.md` § cross-source anomalies |
| A cross-artifact question→tool mapping | `query.md` § question → tool |
| A symptom that should reach a trace, or a side-attribution check | `investigate.md` |
| Resolve scoping, an efficiency delta for joining | `conventions.md` |
| A script bug or new flag | `../../scripts/correlate/*.py` |

## Boundaries specific to this subtree

- **Observation detail belongs to the per-artifact subtree, not here.** A new grep
  for a gNB log line goes to `../ocudu/`, even when you found it while correlating.
  What lands here is the *join*: which key, which two sources, what disagreement
  means.
- **Semantics belong to `../common/`.** If the learning is about what a procedure
  or message *means* rather than how to line two sources up, it goes there and this
  subtree links down to it.
- `correlate/` may link into `../common/` and into the per-type subtrees it joins —
  it is the one subtree permitted to reference siblings. It must **not** link up to
  a `mode-*.md` playbook.
- This subtree deviates from the standard type layout deliberately: reference
  material is flat (no `reference/`), and `procedures/` holds cross-artifact traces
  in place of `troubleshooting/`. Keep it that way unless the whole layout changes.
- **Never** record a run's verdict — RNTIs, UE-IDs, slot numbers, per-run
  narratives. Write the mechanism and the observable signal that discriminates it.
