# pcap memory routing

Loaded during self-maintenance (see `../self-maintenance.md` § Step 2), not during
analysis — where a new `pcap` learning goes.

Match the surrounding format; no dates/timestamps.

- new/changed tshark filter or field → `protocols/<proto>.md` § Key tshark
  filters (or `tshark-recipes.md` if cross-cutting). A changed procedure
  **code/name** is artifact-agnostic → `../common/protocols/<proto>.md`
  § Procedures and codes; also mirror it in `scripts/pcap/utils.py`
  `PROC_CODE_NAMES`, which the overview/proc-code scripts use to print names.
- protocol/procedure **semantics** (message meaning, identifier model, failure
  signature shared across artifacts) → `../common/` (not here); keep only the
  tshark observation in `protocols/<proto>.md`.
- Upper-PDU framing or dissector quirk → `pcap-format.md`
- failure signature → `procedures/<proc>.md` § Failure markers
- cross-protocol correlation pattern → `cross-pcap-correlation.md`
- a new `procedures/<name>.md` → also add a row to `analysis-guide.md`
  § Investigating a failure; a new `scripts/pcap/<name>.py` → document it in
  `analysis-guide.md`, the procedure file, and `protocols/<proto>.md`
  § Parsing script
- a script bug → fix it in `scripts/pcap/*.py`
