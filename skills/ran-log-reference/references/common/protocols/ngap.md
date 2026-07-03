# NGAP — semantics (gNB ↔ AMF, N2 interface)

Artifact-agnostic meaning of the NGAP messages: what each procedure does, which
node initiates it, the identifiers it carries, and the common failure signatures.
**Observation is per-artifact** — tshark filters and field names are in
`../../pcap/protocols/ngap.md`; gNB-log `Rx/Tx PDU` lines are in the `ocudu`
subtree. Spec: TS 38.413 (see `../spec-map.md`).

NGAP carries the control plane between the gNB and the AMF: NG interface setup,
per-UE registration (Initial UE Message → Initial Context Setup), NAS transport,
PDU-session management, paging, and UE-context release. It is the boundary
between the RAN and the 5G core.

## Procedures and codes

| Code | Procedure | Initiator | Meaning |
|---:|---|---|---|
|  0 | AMFConfigurationUpdate | AMF | infrastructure |
|  4 | DownlinkNASTransport | AMF | NAS toward the UE |
| 14 | InitialContextSetup | AMF | completes UE registration; assigns AMF-UE-NGAP-ID |
| 15 | InitialUEMessage | gNB | first NGAP message for a UE |
| 19 | NASNonDeliveryIndication | gNB | NAS could not be delivered |
| 21 | NGSetup | gNB | NG-C setup at startup |
| 24 | Paging | AMF | DL idle-mode paging |
| 28 | PDUSessionResourceRelease | AMF | release a PDU session (carries `cause`, not a failure) |
| 29 | PDUSessionResourceSetup | AMF | establish a PDU session |
| 35 | RANConfigurationUpdate | gNB | infrastructure |
| 40 | UEContextModification | AMF | modify UE context |
| 41 | UEContextRelease | AMF or gNB | end of the UE on NG |
| 44 | UERadioCapabilityInfoIndication | gNB | report UE radio capabilities |
| 46 | UplinkNASTransport | gNB | NAS toward the AMF |

## Identifiers carried

- `RAN-UE-NGAP-ID` — gNB-assigned, present from InitialUEMessage onward.
- `AMF-UE-NGAP-ID` — AMF-assigned, present from InitialContextSetupRequest onward.

Full identifier model (scope, HO stability) in `../identifiers.md`; cross-artifact
joining in `../../correlate/ue-identity-map.md`.

## Failure signatures

- **NGSetupFailure** — gNB rejected by the AMF at startup; check PLMN/TAC config.
- **InitialContextSetupFailure** — AMF rejected the UE; the cause IE distinguishes
  authentication failure, subscription issue, config mismatch.
- **PDUSessionResourceSetupResponse with `failedListPDUSessions`** — UPF or E1AP
  problem; pair with the E1AP BearerContextSetup outcome.
- **UEContextReleaseCommand, cause `radio-connection-with-ue-lost`** —
  AMF-initiated release after the gNB reported RLF.
- **UEContextReleaseCommand, cause `user-inactivity`** — normal idle release, not
  a failure.
- **InitialUEMessage without a following InitialContextSetupRequest** — AMF
  silently dropped the registration; check connectivity / AMF logs.
