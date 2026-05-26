# UE Context Release

UE-context release is initiated either by the AMF (idle release, AMF policy)
or by the gNB (RLF detected). The cause IE distinguishes the two.

## Trigger events

| Initiator | Trigger PDU | File |
|---|---|---|
| AMF | `UEContextReleaseCommand` (procedureCode 41) | `ngap.pcap` |
| gNB | `UEContextReleaseRequest` (procedureCode 40) followed by AMF-side Command | `ngap.pcap` |
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

## Failure markers

| Symptom | Cause hypothesis |
|---|---|
| `UEContextReleaseCommand` with `radio-connection-with-ue-lost` early in run | RLF — check MAC inactivity, RLC retransmission storm in earlier window. |
| No `UEContextReleaseComplete` after Command | DU/CU crash or hang; pair with logs around the same epoch. |
| Release Request with no AMF Command response | NGAP link broken; AMF didn't see the request. |
| F1AP release without NGAP release | CU released the DU side but kept the NGAP context — usually a multi-DU split-decision; double-check it's not a stuck context. |

## tshark filters

```bash
# All NGAP releases with cause
tshark -r ngap.pcap \
    -Y 'ngap.procedureCode == 40 || ngap.procedureCode == 41' \
    -T fields -e frame.number -e frame.time_epoch \
    -e ngap.RAN_UE_NGAP_ID -e ngap.cause

# F1AP releases
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 6'
```

## Cross-references

- `../protocols/ngap.md`, `../protocols/f1ap.md`, `../protocols/e1ap.md`
- `../cross-pcap-correlation.md`

## Accumulated knowledge

*Append: cause-IE values you've seen and how they map to log lines, RLF timing
patterns, AMF release-policy observations.*
