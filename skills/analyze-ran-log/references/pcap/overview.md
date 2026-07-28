# pcap — overview slot

Type-specific slot for the **overview** activity; the driving playbook pulls this
in. Preflight (`SKILL.md` § Resolve & classify) already confirmed each file's
format.

## single pcap

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/pcap_overview.py <file.pcap> --top 5
```

Emits, per pcap:

- packet count, and first/last `frame.time_epoch`
- distinct UE identifiers per ID-type (see `reference/protocols/general.md`)
- top procedure codes — **NGAP/F1AP/E1AP only**; `mac` and `rlc` carry no
  procedure codes, so those pcaps report packets, time range and UE IDs only
- count of `Failure` / `Reject` PDUs — again NGAP/F1AP/E1AP only

The protocol is inferred from the **file stem**, so a pcap not named exactly
`ngap`/`f1ap`/`e1ap`/`mac`/`rlc` (e.g. `gnb_ngap.pcap`) silently degrades to
packets + time range. Rename or symlink it to the bare protocol name first;
resolve already reported which dissector actually bound.

## run directory

Run the one-shot summary — it calls `pcap_overview.py` across every sibling pcap,
then appends the per-protocol UE-ID tables (F1AP/NGAP/E1AP):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/summary.py <run-dir> --top 5
```

(`pcap_overview.py <run-dir>` alone also iterates every sibling pcap, if you only
need the per-pcap overview without the UE-ID tables.)

## summary block

- Input path (single pcap or run directory).
- One line per pcap: packets, time range, top procedures, failure count — **the
  script output verbatim, don't paraphrase**. The scripts print procedures as
  `Name(code)` (e.g. `InitialContextSetup(14)`); for any bare code not yet in the
  map, look it up in `../common/protocols/<proto>.md` § Procedures and codes
  (f1ap, e1ap, ngap — the only protocols with procedure codes).
- Anomalies bulleted last, one each — non-zero failure counts, or sibling pcaps
  with non-overlapping time ranges.

`--top N` truncates the procedure list, so a setup/release imbalance is usually
**not** visible in the overview. To check one deliberately, count both codes
directly rather than inferring from the truncated table:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/extract_proc_codes.py <pcap> --proto ngap
```
