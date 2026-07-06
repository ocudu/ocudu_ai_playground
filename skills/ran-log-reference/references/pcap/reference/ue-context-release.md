# UE Context Release

Pcap observation surface. The artifact-agnostic message ladder + cause-IE values
is `../../common/procedures/ue-release.md`; this file is the pcap view. For
diagnosing an *abnormal* release, see `../troubleshooting/ue-context-release.md`.

UE-context release is initiated either by the AMF (idle release, AMF policy)
or by the gNB (RLF detected). The cause IE distinguishes the two.

## Trigger events

Codes 41 (NGAP UEContextRelease) and 6 (F1AP UEContextRelease) are verified
against an OCUDU capture. Code 42 (NGAP UEContextReleaseRequest) is per TS 38.413
(not present in the sample capture) — check via `tshark -V` if a run exhibits it.

| Initiator | Trigger PDU | File |
|---|---|---|
| AMF | `UEContextReleaseCommand` (procedureCode 41) | `ngap.pcap` |
| gNB | `UEContextReleaseRequest` (procedureCode 42) followed by AMF-side Command | `ngap.pcap` |
| CU (F1) | `UEContextReleaseCommand` (procedureCode 6) on the DU | `f1ap.pcap` |

## Expected sequence — gNB-initiated release on RLF

```
ngap.pcap   UEContextReleaseRequest    (cause: radio-connection-with-ue-lost)
ngap.pcap   UEContextReleaseCommand    (AMF echoes back)
ngap.pcap   UEContextReleaseComplete
f1ap.pcap   UEContextReleaseCommand    (CU → DU)
f1ap.pcap   UEContextReleaseComplete   (DU → CU)
e1ap.pcap   BearerContextReleaseRequest (if user-plane was up)
e1ap.pcap   BearerContextReleaseResponse
```

## Expected sequence — AMF-initiated idle release

```
ngap.pcap   UEContextReleaseCommand    (cause: user-inactivity)
ngap.pcap   UEContextReleaseComplete
f1ap.pcap   UEContextReleaseCommand
f1ap.pcap   UEContextReleaseComplete
```

## Cause-IE values commonly seen

| Cause | Meaning |
|---|---|
| `radio-connection-with-ue-lost` | gNB lost the UE (RLF) |
| `user-inactivity` | Inactivity timer expired (normal idle) |
| `release-due-to-cn-detected-mobility` | AMF detected the UE moved out |
| `unspecified` | Generic; look at surrounding events |
| `release-due-to-pre-emption` | Resource pre-emption by higher-priority traffic |

## Diagnosing failures

For failure markers (abnormal / stuck releases → likely cause) and the tshark
checklist, see `../troubleshooting/ue-context-release.md`.

## Cross-references

- `protocols/ngap.md`, `protocols/f1ap.md`, `protocols/e1ap.md`
- `cross-pcap-correlation.md`
