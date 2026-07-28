# Procedure: PDU session / DRB setup — abstract ladder

The artifact-agnostic message sequence that brings up a UE's user-plane bearers.
It overlaps the tail of the attach (`ue-attach.md` steps 14–17) — the AMF sends
the PDU-session list in `InitialContextSetupRequest`, the gNB requests the bearer
from the CU-UP over E1AP, plumbs the DRBs to the DU over F1AP, and acknowledges
with `PDUSessionResourceSetupResponse`. For a session triggered *after* attach it
starts instead from a standalone NGAP `PDUSessionResourceSetupRequest`. Spec:
NGAP §8.2 / E1AP §8.3.1 (see `../spec-map.md`).

## Message ladder

| # | Message (abstract) | Between | Where seen |
|---:|---|---|---|
| 1 | PDUSessionResourceSetupRequest (or the PDU-session list inside InitialContextSetupRequest) | AMF → gNB | gNB log (NGAP), pcap `ngap` (29) |
| 2 | BearerContextSetupRequest / Response | CU-CP ↔ CU-UP | gNB log (E1), pcap `e1ap` (8) |
| 3 | UEContextModificationRequest / Response (registers DRBs at the DU; DU returns its F1-U DL TEIDs) | CU ↔ DU | gNB log (F1), pcap `f1ap` (7) |
| 4 | BearerContextModificationRequest / Response (feeds the DU DL TEIDs to CU-UP) | CU-CP ↔ CU-UP | gNB log (E1), pcap `e1ap` (9) |
| 5 | RRC Reconfiguration / Complete (carries DRB / RLC-bearer / PDCP config) | gNB ↔ UE | UE log (RRC), gNB log (RRC) |
| 6 | PDUSessionResourceSetupResponse | gNB → AMF | gNB log (NGAP), pcap `ngap` (29) |
| 7 | GTP-U tunnels added (one per direction) | gNB ↔ UPF | gNB log (GTPU) |

After step 7 the user plane is up; the first core DL packet appears as a GTP-U
RX SDU. On the UE side the tell is an `RRC reconfiguration` **without**
`reconfigurationWithSync` (a bearer/measurement update, not a handover).

## Observation & diagnosis

How each step appears, and its per-step failure markers, live in the artifact
subtrees — each links back to this ladder. Protocol-level failure signatures:
`../protocols/e1ap.md`, `../protocols/ngap.md`.
