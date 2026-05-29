# Cross-pcap correlation

OCUDU run directories produce 5 single-protocol pcaps that share a wall-clock
time base. This file describes how to align events across them.

## Time base

All 5 pcaps use the same wall-clock epoch (µs precision). `frame.time_epoch`
is therefore directly comparable across files. There is no per-pcap offset,
no clock skew between protocols — they were all emitted by the same OCUDU
process.

Caveat: a pcap may start later or end earlier than its siblings (e.g. NGAP
captures only begin when the AMF link comes up). When ranges don't overlap,
`correlate_run.py` warns rather than silently mis-aligning.

## Joining events across protocols

The general pattern for a single UE's lifecycle:

```
f1ap.pcap   InitialULRRCMessageTransfer            (T0)
ngap.pcap   InitialUEMessage                       (T0 + a few ms)
ngap.pcap   InitialContextSetupRequest             (T0 + ~AMF delay)
f1ap.pcap   UEContextSetupRequest                  (just before NGAP response)
f1ap.pcap   UEContextSetupResponse
ngap.pcap   InitialContextSetupResponse
e1ap.pcap   BearerContextSetupRequest/Response     (if PDU session set up)
ngap.pcap   PDUSessionResourceSetupRequest/Response
mac.pcap    (data PDUs throughout)
rlc.pcap    (data PDUs throughout)
ngap.pcap   UEContextReleaseCommand
f1ap.pcap   UEContextReleaseCommand/Complete
```

A correlation join is *temporal proximity within a tolerance window* on the
matching UE identifier (when one is available — see § Identifier joining).

## Identifier joining

UE identifiers don't survive across all protocols, so cross-protocol joins
use a hybrid of identifier match (when possible) and temporal adjacency.

| From | To | Join key |
|---|---|---|
| F1AP `gNB-DU-UE-F1AP-ID` | F1AP `gNB-CU-UE-F1AP-ID` | Both fields appear once the CU assigns its ID (UEContextSetupRequest/Response). |
| F1AP `gNB-CU-UE-F1AP-ID` | NGAP `RAN-UE-NGAP-ID` | Same UE → temporal adjacency at registration: F1AP InitialULRRCMessageTransfer ≈ NGAP InitialUEMessage within 50 ms. |
| NGAP `RAN-UE-NGAP-ID` | NGAP `AMF-UE-NGAP-ID` | AMF assigns AMF-UE-NGAP-ID in InitialContextSetupRequest; both appear together from then on. |
| NGAP UE | E1AP `gNB-CU-CP-UE-E1AP-ID` / `gNB-CU-UP-UE-E1AP-ID` | Established at BearerContextSetup. Temporal adjacency with NGAP PDUSessionResourceSetup. |
| F1AP `C-RNTI` (in UEContextSetupRequest) | MAC `mac-nr.rnti` | Direct equality. |

For per-protocol UE lists, run the three protocol-specific scripts against
each pcap individually:

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/f1ap_ue_ids.py <run-dir>/f1ap.pcap
python3 ${CLAUDE_SKILL_DIR}/references/scripts/ngap_ue_ids.py <run-dir>/ngap.pcap
python3 ${CLAUDE_SKILL_DIR}/references/scripts/e1ap_ue_ids.py <run-dir>/e1ap.pcap
```

To join them, eyeball the timestamps (first sightings should align within
50 ms at registration, within a few hundred ms at PDU-session setup) or use
`correlate_run.py` for an event-level timeline.

## Default windows

For investigation drilling around a known failure event at epoch `T_fail`:

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/correlate_run.py <run-dir> \
    --around <T_fail> --window-ms 2000
```

This shows everything in the 2-second window across all 5 pcaps, time-sorted.

Adjust the window:
- Random-access investigations: 50–200 ms is usually enough.
- Handover investigations: 500 ms to a few seconds (preparation + execution).
- AMF / PDU-session timing: extend to several seconds (AMF round-trips).

## Cache

Each helper script caches its tshark field-extraction output as one TSV per
(pcap, column-set) tuple at
`${CLAUDE_CODE_TMPDIR:-/tmp}/claude-skills-${CLAUDE_CODE_SESSION_ID}/pcap-cache-<sha>.tsv`
(sha256 of the canonical pcap path + tag). `correlate_run.py` reads back the
per-protocol caches and joins in-process — re-runs against the same run dir
reuse all the caches and skip tshark entirely. The directory is shared with the
`analyze-amari-ue-log` skill for the lifetime of the Claude session.
