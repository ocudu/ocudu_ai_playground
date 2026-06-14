# pcap conventions

Type-specific deltas for `pcap` artifacts. The shared resolve / efficiency /
memory flow lives in the skill `SKILL.md`; this file carries only what is
particular to Upper-PDU packet captures.

## Resolve & scope

The dispatcher runs `scripts/pcap/resolve.py`, which — per target pcap —
checks it is non-empty, uses the Wireshark **Upper-PDU** (DLT 252) framing, and
binds a known 3GPP dissector (`ngap`/`f1ap`/`e1ap`/`mac-nr`/`rlc-nr`) on the
first frame. It prints the resolved kind, the sibling pcaps present, the tshark
version, and a per-file `OK`/`FAIL` line ending in `verdict: OK`/`BAIL`. **Bail
if the verdict is not OK** — a `FAIL` with an unexpected/missing dissector
usually means the Upper-PDU dispatcher needs `-d user_dlt 252,...`; document such
a case in `pcap-format.md`.

**Scope** — a run directory's five pcaps (`mac`, `rlc`, `f1ap`, `e1ap`, `ngap`)
are one logical capture, cross-correlated by epoch timestamp. For a single pcap:
for a deep investigation, widen to the reported run-dir siblings for
cross-protocol correlation; for a narrow question, stay scoped to the file at
hand.

## Efficiency rules (pcap)

- **Never** run `tshark -V` without `-c 1` or a single-frame filter
  (`-Y 'frame.number == N'`). Full verbose dumps blow up context.
- **Never** pipe an unbounded `tshark -T fields` result into context. Cap at 200
  rows with `head -n 200`; spill the rest into the cache dir as
  `pcap-cache-<sha>.tsv` and report the path.
- **Reuse** the cache: if `pcap-cache-<sha>.tsv` already exists for a given pcap
  and column set, do not re-invoke tshark — post-filter the cached file instead.
- **AppArmor**: on Ubuntu the Canonical AppArmor profile on tshark restricts
  reads to `/tmp`. The helper scripts auto-stage pcaps into the cache dir's
  `pcap-stage/` subfolder — see `pcap-format.md` § AppArmor.
- For run directories with multiple UEs, scope tshark queries by UE identifier
  early — the cross-product of 5 pcaps × many UEs is large.

## Memory routing (pcap)

Match the surrounding format; no dates/timestamps.

- new/changed tshark filter or field/procedure code → `protocols/<proto>.md`
  § Key tshark filters / § Common procedures and codes (or `tshark-recipes.md`
  if cross-cutting). A changed procedure code/name must also be mirrored in
  `scripts/pcap/utils.py` `PROC_CODE_NAMES`, which the overview/proc-code scripts
  use to print names.
- Upper-PDU framing or dissector quirk → `pcap-format.md`
- failure signature → `procedures/<proc>.md` § Failure markers
- cross-protocol correlation pattern → `cross-pcap-correlation.md`
- a new `procedures/<name>.md` → also add a row to `analysis-guide.md`
  § Investigating a failure; a new `scripts/pcap/<name>.py` → document it in
  `analysis-guide.md`, the procedure file, and `protocols/<proto>.md`
  § Parsing script
- a script bug → fix it in `scripts/pcap/*.py`
