# amari-ue memory routing

Loaded during self-maintenance (see `../self-maintenance.md` § Step 2), not during
analysis — where a new `amari-ue` learning goes.

Match the surrounding format; no dates/timestamps.

- new grep recipe → `reference/log-format.md` § Key grep recipes
- new field / keyword / state / event → the matching table in
  `reference/log-format.md` (§ Per-layer format, § NAS state values, § Key PHY
  channel keywords, § RRC channel keywords, § Key RRC message types, § PROD sim
  event types)
- new `amarisoft_ue.cfg` field / quirk → `reference/config-format.md`
  (§ Field reference)
- failure signature / diagnostic step → `troubleshooting/<proc>.md`
  (§ Failure markers or § Investigation checklist); expected sequence /
  vocabulary → `reference/<proc>.md` (§ Expected sequence). Keep the two paired:
  a procedure's `reference/` doc carries the sequence and points to its
  `troubleshooting/` sibling for diagnosis.
- protocol/procedure **semantics** shared across artifacts (a message meaning, an
  abstract procedure ladder, an identifier definition, a spec/FAPI pointer) →
  `../common/` (not here); a `reference/<name>.md` doc keeps only the UE-log
  observation and links to its `../../common/procedures/<name>.md` ladder.
- a new procedure → add the `reference/<name>.md` + `troubleshooting/<name>.md`
  pair and a dispatch row in `investigate.md` § Investigating a failure
  pointing at `troubleshooting/<name>.md`; a new `scripts/amari-ue/<name>.py` →
  document it in `overview.md` / `query.md` and/or the relevant doc
- a script bug → fix it in `scripts/amari-ue/*.py`
