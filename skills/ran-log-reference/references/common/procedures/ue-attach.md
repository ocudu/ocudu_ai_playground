# Procedure: UE attach — abstract ladder

The artifact-agnostic message sequence for an initial attach (RRC connection +
NAS registration + Initial Context Setup). This is *what should happen*; each row
notes which artifact surfaces it. For the exact observation surface — gNB log
lines, tshark filters, UE-log markers — follow the per-artifact docs, which link
back to this ladder. Spec clauses in `../spec-map.md`.

A UE sends PRACH → MSG3 (RRC Setup Request) → RRC Setup → RRC Setup Complete
(carrying the NAS Registration Request). The NAS reaches the AMF; authentication,
NAS security, and capability exchange follow; the AMF issues
`InitialContextSetupRequest`. The gNB sets up the DRBs via F1AP + E1AP and
acknowledges with `InitialContextSetupResponse`, after which the user plane is up.

## Message ladder

| # | Message (abstract) | Between | Where seen |
|---:|---|---|---|
| 1 | PRACH preamble → RA-RNTI/preamble detected | UE → gNB PHY/MAC | UE log (PHY), gNB log (SCHED), pcap `mac` |
| 2 | RAR / MSG2 (UL grant for MSG3) | gNB → UE | gNB log (SCHED) |
| 3 | MSG3 = RRC Setup Request (CCCH) | UE → gNB | UE log (RRC), gNB log (MAC/RRC) |
| 4 | Contention resolution / MSG4 | gNB → UE | gNB log (MAC) |
| 5 | InitialULRRCMessageTransfer (wraps RRC Setup Request) | DU → CU | gNB log (F1), pcap `f1ap` (11) |
| 6 | RRC Setup (via DLRRCMessageTransfer) | CU → UE | UE log (RRC), gNB log (RRC), pcap `f1ap` (12) |
| 7 | RRC Setup Complete (wraps NAS Registration Request) | UE → CU (ULRRCMessageTransfer) | UE log (RRC), gNB log (RRC), pcap `f1ap` (13) |
| 8 | InitialUEMessage (carries NAS Registration Request) | gNB → AMF | gNB log (NGAP), pcap `ngap` (15) |
| 9 | NAS authentication (Down/UplinkNASTransport) | AMF ↔ UE | gNB log (NGAP + RRC info-transfer), pcap `ngap` (4/46) |
| 10 | NAS security mode (Down/UplinkNASTransport) | AMF ↔ UE | gNB log (NGAP), pcap `ngap` |
| 11 | InitialContextSetupRequest (assigns AMF-UE-NGAP-ID) | AMF → gNB | gNB log (NGAP), pcap `ngap` (14) |
| 12 | AS SecurityModeCommand / Complete | gNB ↔ UE | UE log (RRC), gNB log (RRC) |
| 13 | UECapabilityEnquiry / Information | gNB ↔ UE | gNB log (RRC) |
| 14 | UEContextSetupRequest / Response | CU ↔ DU | gNB log (F1), pcap `f1ap` (5) |
| 15 | BearerContextSetupRequest / Response | CU-CP ↔ CU-UP | gNB log (E1), pcap `e1ap` |
| 16 | BearerContextModification (feeds DU F1-U DL TEIDs to CU-UP) | CU-CP → CU-UP | gNB log (E1), pcap `e1ap` |
| 17 | RRC Reconfiguration / Complete (carries DRB config) | gNB ↔ UE | UE log (RRC), gNB log (RRC) |
| 18 | InitialContextSetupResponse | gNB → AMF | gNB log (NGAP), pcap `ngap` (14) |

After step 18 the UE is attached and DRBs are operational — GTP-U SDUs start
flowing. The NAS state machine on the UE walks
`5GMM-NULL` → `REGISTERED-INITIATED` → `REGISTERED` across steps 3–17.

## Observation & diagnosis

How each step appears, and the failure marker per step (which observed step is
missing → likely cause), live in the artifact subtrees — each links back to this
ladder. Protocol-level failure signatures: `../protocols/f1ap.md`,
`../protocols/ngap.md`, `../protocols/e1ap.md`.
