# viavi conventions

Type-specific deltas for `viavi` artifacts (the VIAVI RU-simulator command log).
The shared resolve / efficiency / memory flow lives in the skill `SKILL.md`; this
file carries only what is particular to VIAVI logs.

A VIAVI test produces a single artifact in two forms:

| File | Description |
|---|---|
| `YYMMDD_HHMMSS_Command_Log<NNN>.txt` | The command/event log — commands sent, `C:` responses, and the `I: CMPI` runtime event stream |
| `YYMMDD_HHMMSS_Command_Log<NNN>.zip` | A compressed copy of the **identical** `.txt` — not a distinct artifact |

The VIAVI tester emulates the RU, RF channel, NR UEs, and core; this log is the
control/observation channel for an OCUDU test, not an OCUDU app log. See
`log-format.md` for the full grammar.

## Resolve & scope

The dispatcher runs `scripts/viavi/resolve.py`, which accepts the `.txt`, the
`.zip`, or a directory containing either, and resolves to the command-log file
(newest if several; the `.txt` is preferred over its identical `.zip`). It
confirms the file is non-empty and carries the VIAVI signature (`RSET` / `C: RSET
0x00 Ok` / `I: CMPI` in the first lines), then prints the path, format, size, and
a `verdict:` line. **Bail if the verdict is not OK.**

**Scope** — a single command log already aggregates *all* simulated UEs (this
example: 100 UE Ids, 0–119). Scope queries by `UE Id` early; the per-UE
cross-product over a multi-hour run is large.

## Efficiency rules (viavi)

- **Never** read the raw `.txt` into context — it can be hundreds of thousands of
  lines (this example: 655k lines / 55 MB). Use the helper scripts or grep.
- The file has **CRLF** endings and some **non-UTF-8 bytes** — always grep with
  `LC_ALL=C grep -a`; the helper scripts already strip CR and use
  `errors="replace"`.
- Read the `.zip` in place (the scripts do, via `zipfile`); don't extract a
  55 MB `.txt` to disk just to grep it.
- Spill larger results to `<cache-dir>/viavi-<purpose>-<sha>.txt` (use the
  `viavi-` prefix) and report the path.
- Most of the file is **continuation lines** (GETSTATS rows, `Cell Info:`
  bodies); use `viavi_log_search.py` (block-aware) rather than line greps when
  you need whole records.

## Memory routing (viavi)

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
