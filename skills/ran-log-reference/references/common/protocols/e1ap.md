# E1AP — semantics (CU-CP ↔ CU-UP, E1 interface)

Artifact-agnostic meaning of the E1AP messages: what each procedure does, which
node initiates it, the identifiers it carries, and the common failure signatures.
**Observation is per-artifact** — tshark filters and field names are in
`../../pcap/protocols/e1ap.md`; gNB-log `Rx/Tx PDU` lines are in the `ocudu`
subtree. Spec: TS 38.463 (see `../spec-map.md`).

E1AP carries the control plane between the gNB-CU-CP and gNB-CU-UP: it manages
bearer contexts and PDU-session resources on the user-plane side. It is the data-
path counterpart of the NGAP PDU-session procedures — when a UE attaches fine via
NGAP but throughput is zero, the fault is usually here.

## Procedures and codes

| Code | Procedure | Initiator | Meaning |
|---:|---|---|---|
|  3 | gNB-CU-UP-E1Setup | CU-UP | E1 link setup from the CU-UP side |
|  4 | gNB-CU-CP-E1Setup | CU-CP | E1 link setup from the CU-CP side |
|  5 | gNB-CU-UP-ConfigurationUpdate | CU-UP | infrastructure |
|  6 | gNB-CU-CP-ConfigurationUpdate | CU-CP | infrastructure |
|  7 | E1Release | either | E1 link teardown |
|  8 | BearerContextSetup | CU-CP | create a user-plane bearer |
|  9 | BearerContextModification | CU-CP | add/remove DRBs, change QoS |
| 10 | BearerContextModificationRequired | CU-UP | CU-UP-initiated change |
| 11 | BearerContextRelease | CU-CP | tear down the user plane |
| 12 | BearerContextReleaseRequest | CU-UP | CU-UP-initiated release |

## Identifiers carried

- `gNB-CU-CP-UE-E1AP-ID` — CU-CP-assigned.
- `gNB-CU-UP-UE-E1AP-ID` — CU-UP-assigned (after BearerContextSetupResponse).
- `pDU_Session_ID` — per-PDU-session selector.
- `dRB_ID` — per-DRB selector (when DRB-level granularity is in play).
- GTP-U TEIDs for the user plane appear inside the BearerContextSetup IEs.

Full identifier model (scope, HO stability) in `../identifiers.md`; cross-artifact
joining in `../../correlate/ue-identity-map.md`.

## Failure signatures

- **BearerContextSetupFailure** — CU-UP could not accept the bearer; read the
  cause IE (resources unavailable, UPF unreachable, TNL address mismatch).
- **No BearerContextSetup despite an NGAP PDUSessionResourceSetupRequest** —
  CU-CP didn't forward to CU-UP; check the E1 link state.
- **BearerContextReleaseRequest mid-session** — CU-UP terminated the bearer
  itself (overload, link failure, configuration error).
- **E1SetupFailure** — CU-CP and CU-UP didn't agree at startup (capabilities,
  supported S-NSSAIs).
