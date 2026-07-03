# E1AP — pcap observation (CU-CP ↔ CU-UP, E1 interface)

How E1AP shows up in `e1ap.pcap` and how to query it. The **semantics** —
procedure-code meanings, identifier model, failure signatures — are
artifact-agnostic and live in `../../common/protocols/e1ap.md`; this file is the
tshark/observation layer only.

Use `e1ap.pcap` to diagnose data-path setup problems when the UE attaches fine
via NGAP but throughput is zero or PDU-session setup fails.

## Key tshark filters

```bash
# All E1AP messages with both UE IDs
tshark -r e1ap.pcap \
    -T fields -E separator=$'\t' \
    -e frame.number -e frame.time_epoch \
    -e e1ap.procedureCode \
    -e e1ap.GNB_CU_CP_UE_E1AP_ID -e e1ap.GNB_CU_UP_UE_E1AP_ID

# Bearer context lifecycle (codes/meanings: ../../common/protocols/e1ap.md)
tshark -r e1ap.pcap -Y 'e1ap.procedureCode in {8,9,10,11,12}'

# Specific procedures
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 8'    # BearerContextSetup
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 9'    # BearerContextModification
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 11'   # BearerContextRelease
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 3'    # gNB-CU-UP-E1Setup
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 7'    # E1Release
```

## Identifier fields (tshark)

- `e1ap.GNB_CU_CP_UE_E1AP_ID` — CU-CP-assigned.
- `e1ap.GNB_CU_UP_UE_E1AP_ID` — CU-UP-assigned (after BearerContextSetupResponse).
- `e1ap.pDU_Session_ID` — per-PDU-session selector.
- `e1ap.dRB_ID` — per-DRB selector.
- GTP-U TEIDs for the user plane appear inside the BearerContextSetup IEs.
- See `../cross-pcap-correlation.md` for joining to NGAP / F1AP, and
  `../../common/identifiers.md` for the identifier model.

## Parsing script

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/extract_proc_codes.py <e1ap.pcap> --proto e1ap
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/correlate_run.py <run-dir> --protocols e1ap
```
