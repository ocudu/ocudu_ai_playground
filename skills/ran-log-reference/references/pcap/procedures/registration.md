# UE Registration (initial attach)

Pcap observation surface. The artifact-agnostic attach message ladder is
`../../common/procedures/ue-attach.md`; this file is the across-pcaps view of it.

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
| `InitialULRRCMessageTransfer` but no `InitialUEMessage` in NGAP | CU didn't forward to AMF (check CU-CP log; AMF link may be down), **or** the CU rejected the UE at RRC setup — see the empty-container / rrcReject rows below. |
| `InitialULRRCMessageTransfer` carries an **empty `DUtoCURRCContainer`** (IE present but zero-length) | DU can't admit the UE — no dedicated resources, commonly the cell PUCCH resource pool (`nof_cell_sr_resources`/`nof_cell_csi_resources`) exhausted under many-UE load. Per TS 38.473 §8.4.1.2 the DU signals "can't serve" via the empty container; the CU then rejects. No `InitialUEMessage` follows. |
| `UEContextReleaseCommand` with an `rrcReject` `RRCContainer` on `SRBID=0`, right after an `InitialULRRCMessageTransfer` and with no `UEContextSetup` for that UE | CU rejected the RRC connection (admission). The rrcReject carries a wait timer (default 16 s) → the UE backs off and re-RACHes (RACH churn). tshark does **not** dissect this reject — decode it with `f1ap_messages.py` (see `../protocols/f1ap.md` § RRC PDUs inside F1AP containers). |
| `InitialUEMessage` but no `InitialContextSetupRequest` | AMF dropped the registration; check AMF reachability and PLMN config. |
| `InitialContextSetupRequest` with cause IE in subsequent failure | AMF rejected — read the cause IE. Common: authentication failure, illegal subscriber, no S-NSSAI match. |
| `UEContextSetupFailure` from DU | DU couldn't admit the UE — no C-RNTI, cell barred, requested SRB/DRB conflict. |
| `InitialContextSetupResponse` not sent because UEContextSetup failed | The two are paired — CU only responds to AMF after DU confirms. |

## tshark filters

```bash
# NGAP registration-relevant procedures, one UE
# (15 = InitialUEMessage, 14 = InitialContextSetup, 46 = UplinkNASTransport,
#  4 = DownlinkNASTransport — all verified against OCUDU ngap.pcap)
tshark -r ngap.pcap \
    -Y 'ngap.RAN_UE_NGAP_ID == <N> && (ngap.procedureCode == 15 || ngap.procedureCode == 14 || ngap.procedureCode == 46 || ngap.procedureCode == 4)'

# F1AP UE context setup outcomes
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 5'

# Admission rejects (empty DU-to-CU container → rrcReject), invisible to grep -V
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/f1ap_messages.py <f1ap.pcap> | grep rrcReject

# Use the unified timeline for one UE
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/correlate_run.py <run-dir> --ue <ngap-ran-ue-id>
```

## Cross-references

- `../protocols/ngap.md` — NGAP procedure codes and cause IEs.
- `../protocols/f1ap.md` — F1AP UE-context lifecycle.
- `../cross-pcap-correlation.md`.
