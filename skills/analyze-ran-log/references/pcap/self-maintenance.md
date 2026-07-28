# pcap memory routing

Loaded during self-maintenance (see `../self-maintenance.md` § Step 2), not during
analysis — where a new `pcap` learning goes.

Match the surrounding format; no dates/timestamps.

- new/changed tshark filter or field → `reference/protocols/<proto>.md` § Key
  tshark filters (or `reference/tshark-recipes.md` if cross-cutting). A changed
  procedure **code/name** is artifact-agnostic → `../common/protocols/<proto>.md`
  § Procedures and codes; also mirror it in `scripts/pcap/utils.py`
  `PROC_CODE_NAMES`, which the overview/proc-code scripts use to print names.
- protocol/procedure **semantics** (message meaning, identifier model, failure
  signature shared across artifacts) → `../common/` (not here); keep only the
  tshark observation in `reference/protocols/<proto>.md`.
- Upper-PDU framing or dissector quirk → `reference/pcap-format.md`
- failure marker / tshark checklist step → `troubleshooting/<proc>.md`;
  expected across-pcaps sequence or trigger/cause-IE vocabulary →
  `reference/<proc>.md`. Keep the two paired: a `reference/` doc carries the
  sequence and points to its `troubleshooting/` sibling for diagnosis.
- cross-protocol correlation pattern → `reference/cross-pcap-correlation.md`
- a new procedure → add the `reference/<name>.md` + `troubleshooting/<name>.md`
  pair and a dispatch row to `investigate.md` § Investigating a failure
  pointing at the `troubleshooting/<name>.md`; a new `scripts/pcap/<name>.py` →
  document it in `overview.md` / `query.md`, the `troubleshooting/` doc, and
  `reference/protocols/<proto>.md` § Parsing script
- a script bug → fix it in `scripts/pcap/*.py`
