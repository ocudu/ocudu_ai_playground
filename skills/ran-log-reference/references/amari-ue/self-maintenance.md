# amari-ue memory routing

Loaded during self-maintenance (see `../self-maintenance.md` § Step 2), not during
analysis — where a new `amari-ue` learning goes.

Match the surrounding format; no dates/timestamps.

- new grep recipe → `log-format.md` § Key grep recipes
- new field / keyword / state / event → the matching table in `log-format.md`
  (§ Per-layer format, § NAS state values, § Key PHY channel keywords,
  § RRC channel keywords, § Key RRC message types, § PROD sim event types)
- new `amarisoft_ue.cfg` field / quirk → `config-format.md` (§ Field reference)
- failure signature / diagnostic step → `procedures/<proc>.md`
  (§ Investigation checklist or § Expected sequence)
- protocol/procedure **semantics** shared across artifacts (a message meaning, an
  abstract procedure ladder, an identifier definition, a spec/FAPI pointer) →
  `../common/` (not here); a `procedures/<name>.md` doc keeps only the UE-log
  observation and links to its `../common/procedures/<name>.md` ladder.
- a new `procedures/<name>.md` → also add a row to `analysis-guide.md`
  § Investigating a failure; a new `scripts/amari-ue/<name>.py` → document it in
  `analysis-guide.md` and/or the procedure file
- a script bug → fix it in `scripts/amari-ue/*.py`
