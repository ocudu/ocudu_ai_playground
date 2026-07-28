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
- top procedure codes (NGAP/F1AP/E1AP) or PDU types (MAC/RLC)
- count of `Failure` / `Reject` PDUs

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
  map, look it up in the protocol's code table — `../common/protocols/<proto>.md`
  § Procedures and codes for the migrated protocols (f1ap, e1ap, ngap), else
  `reference/protocols/<proto>.md` § Common procedures and codes (mac, rlc).
- Anomalies bulleted last, one each — non-zero failure counts, unbalanced
  setup/release procedure tallies, sibling pcaps with non-overlapping time ranges.
