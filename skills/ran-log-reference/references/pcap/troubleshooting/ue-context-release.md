# Troubleshooting: UE Context Release

A release is abnormal or stuck — an early RLF-caused release, a Command with no
Complete, or an F1AP release with no NGAP counterpart. For the **expected
sequences** (gNB-initiated on RLF, AMF-initiated idle) and the cause-IE
vocabulary this walks against, see `../reference/ue-context-release.md`.

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
    -Y 'ngap.procedureCode == 42 || ngap.procedureCode == 41' \
    -T fields -e frame.number -e frame.time_epoch \
    -e ngap.RAN_UE_NGAP_ID -e ngap.cause

# F1AP releases
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 6'
```

## Cross-references

- `../reference/ue-context-release.md` — the expected release sequences + cause-IE table this walks against.
- `../reference/protocols/ngap.md`, `../reference/protocols/f1ap.md`, `../reference/protocols/e1ap.md`
- `../reference/cross-pcap-correlation.md`
