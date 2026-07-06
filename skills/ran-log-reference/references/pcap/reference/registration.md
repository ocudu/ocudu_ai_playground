# UE Registration (initial attach)

Pcap observation surface. The artifact-agnostic attach message ladder is
`../../common/procedures/ue-attach.md`; this file is the across-pcaps view of it.
For diagnosing a *failed* registration, see `../troubleshooting/registration.md`.

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

## Diagnosing failures

For failure markers (including the empty-`DUtoCURRCContainer` / `rrcReject`
admission rejects) and the tshark checklist, see
`../troubleshooting/registration.md`.

## Cross-references

- `protocols/ngap.md` — NGAP procedure codes and cause IEs.
- `protocols/f1ap.md` — F1AP UE-context lifecycle.
- `cross-pcap-correlation.md`.
