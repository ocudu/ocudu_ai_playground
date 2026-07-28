# ocudu memory routing

Loaded during self-maintenance (see `../self-maintenance.md` § Step 2), not during
analysis — where a new `ocudu` learning goes.

Match the surrounding format; no dates/timestamps.

- new grep recipe → `reference/log-format.md` § Key grep recipes
- new layer / message / keyword → the matching table in `reference/log-format.md`
  (§ Layer tags, § Procedure markers, § Common structured fields)
- UCI outcome vocabulary (ACK/NACK/DTX, SR positive/negative, CSI valid/invalid,
  detection-status codes) → `reference/uci.md`
- new YAML field / quirk → `reference/config-format.md` (§ Sections,
  § Common overrides, § Field reference)
- failure markers / investigation checklist (incl. for a procedure) →
  `troubleshooting/<name>.md`; expected-sequence or vocabulary detail →
  `reference/<name>.md` (§ Expected sequence for procedure docs, or the
  doc's relevant section). Keep the two paired: a procedure's `reference/` doc
  carries the sequence and points to its `troubleshooting/` sibling for diagnosis.
- protocol/procedure **semantics** shared across artifacts (a message meaning, an
  abstract procedure ladder, an identifier definition, a spec/FAPI pointer) →
  `../common/` (not here); a `reference/<name>.md` doc keeps only the gNB-log
  observation and links to its ladder there — from the `reference/` subdir that is
  `../../common/procedures/<name>.md`.
- a new symptom-reachable playbook → add a dispatch row to `investigate.md`
  § symptom → playbook pointing at the `troubleshooting/<name>.md` (which in
  turn cites its `reference/` sequence sibling); a new `scripts/ocudu/<name>.py` →
  document it in `overview.md` / `query.md` and/or the relevant doc
- how/where to load the OCUDU source tree (locations, permission model,
  navigation) → `source-code.md`
- a script bug → fix it in `scripts/ocudu/*.py`
