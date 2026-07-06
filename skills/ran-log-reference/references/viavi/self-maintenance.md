# viavi memory routing

Loaded during self-maintenance (see `../self-maintenance.md` § Step 2), not during
analysis — where a new `viavi` learning goes.

Match the surrounding format; no dates/timestamps, no run-specific values.

- new grep recipe → `log-format.md` § Key grep recipes
- new command token / `C:` code / line class → the matching table in
  `log-format.md` (§ Setup / framing commands, § Payload classes)
- new `I: CMPI` event signature → `log-format.md` § CMPI events
- new GETSTATS field / block detail → `log-format.md` § GETSTATS dump
- failure signature / diagnostic step → `procedures/<proc>.md`
  (§ Investigation checklist or § Expected sequence)
- protocol/procedure **semantics** shared across artifacts (a message meaning, an
  abstract procedure ladder, an identifier definition, a spec/FAPI pointer) →
  `../common/` (not here); a `procedures/<name>.md` doc keeps only the VIAVI-log
  observation and links to its `../common/procedures/<name>.md` ladder.
- a new `procedures/<name>.md` → also add a row to `analysis-guide.md`
  § Investigating a failure; a new `scripts/viavi/<name>.py` → document it in
  `analysis-guide.md` and/or the procedure file
- a script bug → fix it in `scripts/viavi/*.py`
