# PDU Session Resource Setup

Pcap observation surface. The artifact-agnostic message ladder is
`../../common/procedures/pdu-session-setup.md`; this file is the across-pcaps view.
For diagnosing a *failed* PDU session setup, see
`../troubleshooting/pdu-session-setup.md`.

Establishes the user-plane bearers after a UE has registered. Spans NGAP,
E1AP, and F1AP.

## Trigger event

`ngap.pcap` contains `PDUSessionResourceSetupRequest` (procedure code 29)
from the AMF.

## Expected sequence across pcaps

```
ngap.pcap   PDUSessionResourceSetupRequest                  (T0)
e1ap.pcap   BearerContextSetupRequest                       (T0 + a few ms)
e1ap.pcap   BearerContextSetupResponse                      (T0 + tens of ms)
f1ap.pcap   UEContextModificationRequest                    (DRBs added)
f1ap.pcap   UEContextModificationResponse
ngap.pcap   PDUSessionResourceSetupResponse
```

DRB traffic appears in `rlc.pcap` (and corresponding scheduling in `mac.pcap`)
once the user plane is up.

## Diagnosing failures

For failure markers (which step is missing → likely cause) and the tshark
checklist, see `../troubleshooting/pdu-session-setup.md`.

## Cross-references

- `protocols/ngap.md`
- `protocols/e1ap.md`
- `protocols/f1ap.md`
