# Overview mode

Produce a quick factual summary of the capture without diving into individual
packets. Do not ask `AskUserQuestion` mid-flow.

## Phase A — capinfos roll-up

For each input pcap:

```bash
capinfos -aeu <file.pcap>
```

Collect: packet count, capture duration, earliest and latest packet times.
If a run directory was provided, run this for all 5 sibling pcaps.

## Phase B — per-protocol scan

Run the overview helper:

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/pcap_overview.py <pcap-or-dir> --top 5
```

This emits, per pcap:

- packet count
- first and last `frame.time_epoch`
- distinct UE identifiers (per-protocol fields, see `references/protocols/general.md`)
- top procedure codes (NGAP/F1AP/E1AP) or PDU types (MAC/RLC)
- count of `Failure` / `Reject` / `Release with cause` PDUs

## Phase C — sibling roll-up (run directory only)

If the input was a run dir, additionally produce:

- NGAP procedures observed, with counts (e.g. `InitialContextSetup x N`,
  `PDUSessionResourceSetup x M`, `UEContextRelease x K`).
- F1AP UE contexts created and released.
- E1AP bearer contexts created and released.
- Time-aligned headline: first NGAP packet, first F1AP packet, last release,
  capture span.

## Phase D — summary block

Output a single concise summary in this shape:

```
## Capture summary
- Input: <path>            (run directory | single pcap)
- Duration: <H:MM:SS>      from <ISO> to <ISO>
- Files: mac (X pkts), rlc (Y pkts), f1ap (Z pkts), e1ap (W pkts), ngap (V pkts)

## Activity
- UEs observed: <count> (RAN-UE-NGAP-IDs: …)
- NGAP procedures: <top with counts>
- F1AP UE contexts: <created> setup, <released> released
- E1AP bearer contexts: <created> setup, <released> released
- Failures / Rejects: <count, with first epoch>

## Anomalies (if any)
- <one bullet per Failure/Reject/unexpected release>
```

## Phase E — optional escalation

If Phase D surfaced one or more anomalies, end with a single `AskUserQuestion`
offering:

- **Investigate** — switch to investigation mode on the first anomaly.
- **Query** — ask a specific question about the capture.
- **Done** — no further analysis.

Do **not** ask if Phase D was clean. End the turn with the summary.

## Exit criteria

Summary delivered (and, if escalated, the user chose Done or moved to another
mode). Nothing is written to `references/` from overview mode unless a new
generalisable insight emerged — e.g. a previously unseen dissector binding.
