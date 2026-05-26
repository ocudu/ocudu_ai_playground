# UE Registration (initial attach)

## Trigger event

`f1ap.pcap` contains an `InitialULRRCMessageTransfer` carrying an RRC Setup
Request; this then drives the CU to send `InitialUEMessage` to the AMF.

## Expected sequence across pcaps

```
f1ap.pcap   InitialULRRCMessageTransfer        (T0)
f1ap.pcap   DLRRCMessageTransfer (RRC Setup)   (T0 + tens of ms)
f1ap.pcap   ULRRCMessageTransfer (RRC Setup Complete carrying NAS)  (T0 + ~100 ms)
ngap.pcap   InitialUEMessage                   (just after the above)
ngap.pcap   DownlinkNASTransport (Auth Req)    (T0 + AMF RTT)
ngap.pcap   UplinkNASTransport   (Auth Resp)
ngap.pcap   DownlinkNASTransport (Security Mode Cmd)
ngap.pcap   UplinkNASTransport   (Security Mode Complete)
ngap.pcap   InitialContextSetupRequest         (AMF assigns AMF-UE-NGAP-ID)
f1ap.pcap   UEContextSetupRequest              (CU to DU)
f1ap.pcap   UEContextSetupResponse
ngap.pcap   InitialContextSetupResponse
```

## Failure markers

| Symptom | Cause hypothesis |
|---|---|
| `InitialULRRCMessageTransfer` but no `InitialUEMessage` in NGAP | CU didn't forward to AMF — check CU-CP log; AMF link may be down. |
| `InitialUEMessage` but no `InitialContextSetupRequest` | AMF dropped the registration; check AMF reachability and PLMN config. |
| `InitialContextSetupRequest` with cause IE in subsequent failure | AMF rejected — read the cause IE. Common: authentication failure, illegal subscriber, no S-NSSAI match. |
| `UEContextSetupFailure` from DU | DU couldn't admit the UE — no C-RNTI, cell barred, requested SRB/DRB conflict. |
| `InitialContextSetupResponse` not sent because UEContextSetup failed | The two are paired — CU only responds to AMF after DU confirms. |

## tshark filters

```bash
# NGAP registration-relevant procedures, one UE
# (15 = InitialUEMessage, 14 = InitialContextSetup — verified against OCUDU;
#  46 = UplinkNASTransport, 47 = DownlinkNASTransport — 3GPP standard, not
#  yet verified locally)
tshark -r ngap.pcap \
    -Y 'ngap.RAN_UE_NGAP_ID == <N> && (ngap.procedureCode == 15 || ngap.procedureCode == 14 || ngap.procedureCode == 46 || ngap.procedureCode == 47)'

# F1AP UE context setup outcomes
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 5'

# Use the unified timeline for one UE
python3 ${CLAUDE_SKILL_DIR}/references/scripts/correlate_run.py <run-dir> --ue <ngap-ran-ue-id>
```

## Cross-references

- `../protocols/ngap.md` — NGAP procedure codes and cause IEs.
- `../protocols/f1ap.md` — F1AP UE-context lifecycle.
- `../cross-pcap-correlation.md`.

## Accumulated knowledge
