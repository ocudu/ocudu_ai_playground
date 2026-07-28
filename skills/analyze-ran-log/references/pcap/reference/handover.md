# Handover (HO)

Pcap observation surface. The artifact-agnostic message ladder + variants is
`../../common/procedures/handover.md`; this file is the pcap view. For diagnosing
a *failed* handover, see `../troubleshooting/handover.md`.

Handover variants seen in OCUDU tests:

- **Intra-CU intra-DU** — same DU, same cell-group, target cell change only.
- **Intra-CU inter-DU** — source DU → target DU, both under one CU.
- **Inter-CU (N2)** — source gNB → target gNB via AMF (`HandoverRequired` over
  NGAP).

Each is signalled differently. The test name in the run-directory path is the
clearest indicator (`intra_ru_ho`, `inter_ru_ho`).

## Trigger events

| Variant | Trigger PDU | File |
|---|---|---|
| Intra-CU intra-DU | `UEContextModificationRequest` carrying RRC reconfiguration | `f1ap.pcap` |
| Intra-CU inter-DU | `UEContextSetupRequest` on the target DU | `f1ap.pcap` |
| Inter-CU | `HandoverRequired` (HandoverPreparation, procedureCode 12) | `ngap.pcap` |

## First F1AP message ≠ attach indicator

A UE's first F1AP message identifies *how it arrived on the DU*, not whether
the run is a handover scenario:

- `InitialULRRCMessageTransfer` (proc 11) — UE attached via RACH on this DU.
  The DU is acting as a *source* (or as the only) DU for this UE.
- `UEContextSetup` (proc 5) — UE was *handed over* to this DU from another
  DU under the same CU. There is no preceding RACH on this DU. The C-RNTI
  in the UEContextSetupRequest is a fresh allocation for the target cell.

In a single `f1ap.pcap` capture from an inter-DU HO test, source-side UEs
appear first via `InitialULRRCMessageTransfer`, target-side UEs appear first
via `UEContextSetup`. Don't treat the first-message variation as a finding
on its own; cross-check the surrounding `UEContextModificationRequest` /
`UEContextRelease` events to confirm which role this DU is playing.

## Expected sequence — intra-CU inter-DU HO with CFRA

```
f1ap.pcap (src DU)  UEContextModificationRequest (HO prep)     (T0)
f1ap.pcap (tgt DU)  UEContextSetupRequest                      (T0 + tens of ms)
f1ap.pcap (tgt DU)  UEContextSetupResponse                     (T0 + ~100 ms)
mac.pcap (tgt)      RAR for CFRA preamble (TC-RNTI = X')       (T0 + ~100 ms)
mac.pcap (tgt)      DL MAC PDU on RNTI = X' (RRCReconfigComplete) (T0 + ~150 ms)
f1ap.pcap (tgt)     ULRRCMessageTransfer (RRCReconfigComplete) (T0 + ~150 ms)
f1ap.pcap (src)     UEContextReleaseCommand                    (T0 + ~150 ms)
f1ap.pcap (src)     UEContextReleaseComplete                   (T0 + ~200 ms)
```

## Diagnosing failures

For failure markers (which step is missing → likely cause) and the tshark
checklist, see `../troubleshooting/handover.md`.

## Cross-references

- `protocols/ngap.md`, `protocols/f1ap.md`, `protocols/mac.md`
- `cross-pcap-correlation.md`
