# viavi memory routing

Loaded during self-maintenance (see `../self-maintenance.md` § Step 2), not during
analysis — where a new `viavi` learning goes.

Match the surrounding format; no dates/timestamps, no run-specific values.

- new grep recipe → `reference/log-format.md` § Key grep recipes
- new command token / `C:` code / line class → the matching table in
  `reference/log-format.md` (§ Setup / framing commands, § Payload classes)
- new `I: CMPI` event signature → `reference/log-format.md` § CMPI events
- new GETSTATS field / block detail → `reference/log-format.md` § GETSTATS dump
- failure signature / diagnostic step → `troubleshooting/<proc>.md`
  (§ Failure markers or § Investigation checklist)
- expected message sequence / VIAVI vocabulary (line shapes, counting) →
  `reference/<proc>.md`, its paired sequence/vocabulary doc
- protocol/procedure **semantics** shared across artifacts (a message meaning, an
  abstract procedure ladder, an identifier definition, a spec/FAPI pointer) →
  `../common/` (not here); a `reference/<name>.md` doc keeps only the VIAVI-log
  observation and links to its `../common/procedures/<name>.md` ladder.
- a new procedure → add the paired `reference/<name>.md` (expected sequence +
  vocabulary) and `troubleshooting/<name>.md` (failure markers + checklist), and
  add a row to `investigate.md` § symptom → playbook; a new
  `scripts/viavi/<name>.py` → document it in `overview.md` / `query.md` and/or the
  procedure file
- a script bug → fix it in `scripts/viavi/*.py`
