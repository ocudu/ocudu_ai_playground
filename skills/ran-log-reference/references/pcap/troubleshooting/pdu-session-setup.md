# Troubleshooting: PDU Session Resource Setup

The user-plane bearers never come up after registration — the NGAP request has no
matching response, or an E1AP/F1AP setup fails. For the **expected across-pcaps
sequence** this walks against, see `../reference/pdu-session-setup.md`.

## Failure markers

| Symptom | Cause hypothesis |
|---|---|
| `PDUSessionResourceSetupResponse` with `failedListPDUSessions` | UPF / TNL / E1AP problem; inspect E1AP cause. |
| `BearerContextSetupFailure` from CU-UP | CU-UP can't accept the bearer — resources, TNL endpoint, S-NSSAI mismatch. |
| `BearerContextSetupResponse` but no UE traffic afterwards | User plane established at signalling level but UPF not delivering; not visible in pcap — check UPF/core logs. |
| `UEContextModificationFailure` from DU | DU can't add the requested DRBs — usually a configuration or scheduling-pool limit. |
| No E1AP traffic at all for this UE after NGAP request | CU-CP didn't decide to route to CU-UP — check E1 link state. |

## tshark filters

```bash
# NGAP PDU-session procedures for one UE
# (29 = PDUSessionResourceSetup, verified; 28 = ResourceNotify, 30 = ResourceRelease — standard)
tshark -r ngap.pcap \
    -Y '(ngap.procedureCode == 29 || ngap.procedureCode == 30 || ngap.procedureCode == 28) && ngap.RAN_UE_NGAP_ID == <N>'

# E1AP bearer-context lifecycle (codes 8..12 — verified against an OCUDU pcap)
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 8 || e1ap.procedureCode == 9 || e1ap.procedureCode == 10 || e1ap.procedureCode == 11 || e1ap.procedureCode == 12'

# Unified timeline around the request
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/correlate_run.py <run-dir> --around <T0> --window-ms 5000
```

## Cross-references

- `../reference/pdu-session-setup.md` — the expected sequence this walks against.
- `../reference/protocols/ngap.md`
- `../reference/protocols/e1ap.md`
- `../reference/protocols/f1ap.md`
