# E1AP — CU-CP ↔ CU-UP (E1 interface)

## Purpose

E1AP carries the control plane between the gNB-CU-CP and gNB-CU-UP. It
manages bearer contexts and PDU session resources on the user-plane side.
Use `e1ap.pcap` to diagnose data-path setup problems when the UE attaches
fine via NGAP but throughput is zero or PDU session setup fails.

## Key tshark filters

```bash
# All E1AP messages with both UE IDs (note the uppercase G in GNB_*)
tshark -r e1ap.pcap \
    -T fields -E separator=$'\t' \
    -e frame.number -e frame.time_epoch \
    -e e1ap.procedureCode \
    -e e1ap.GNB_CU_CP_UE_E1AP_ID -e e1ap.GNB_CU_UP_UE_E1AP_ID

# Bearer context lifecycle (codes verified against an OCUDU pcap)
tshark -r e1ap.pcap -Y 'e1ap.procedureCode in {8,9,10,11,12}'

# Specific procedures
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 8'    # BearerContextSetup
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 9'    # BearerContextModification
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 11'   # BearerContextRelease
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 3'    # gNB-CU-UP-E1Setup
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 7'    # E1Release
```

## Identifier mapping

- `e1ap.GNB_CU_CP_UE_E1AP_ID` — CU-CP-assigned. **Note the uppercase G**
  in the tshark field name; the lowercase `e1ap.gNB_CU_CP_UE_E1AP_ID` is a
  different (unpopulated) dissector field.
- `e1ap.GNB_CU_UP_UE_E1AP_ID` — CU-UP-assigned (after BearerContextSetupResponse).
- Bearer / PDU-session ID fields:
  - `e1ap.pDU_Session_ID` — per-PDU-session selector.
  - `e1ap.dRB_ID` — per-DRB selector (when DRB-level granularity is in play).
- GTP-U TEIDs for the user plane appear inside the BearerContextSetup IEs.

## Common procedures and codes

Verified against an OCUDU `e1ap.pcap` capture:

| Code | Procedure | Initiator | Notes |
|---:|---|---|---|
|  3 | gNB-CU-UP-E1Setup | CU-UP | E1 link setup from CU-UP side |
|  4 | gNB-CU-CP-E1Setup | CU-CP | E1 link setup from CU-CP side |
|  5 | gNB-CU-UP-ConfigurationUpdate | CU-UP | |
|  6 | gNB-CU-CP-ConfigurationUpdate | CU-CP | |
|  7 | E1Release | either | E1 link teardown |
|  8 | bearerContextSetup | CU-CP | create user-plane bearer |
|  9 | bearerContextModification | CU-CP | add/remove DRBs, change QoS |
| 10 | bearerContextModificationRequired | CU-UP | CU-UP-initiated change |
| 11 | bearerContextRelease | CU-CP | tear down user-plane |
| 12 | bearerContextReleaseRequest | CU-UP | CU-UP-initiated release |

## Common failure signatures

- **BearerContextSetupFailure**: CU-UP could not accept the bearer — check
  cause IE; common reasons: resources unavailable, UPF unreachable, TNL
  address mismatch.
- **No BearerContextSetup at all despite NGAP PDUSessionResourceSetupRequest**:
  CU-CP didn't forward to CU-UP — check CU-CP log for E1 link state.
- **BearerContextReleaseRequest mid-session**: CU-UP terminated the bearer
  itself (overload, link failure, configuration error).
- **E1SetupFailure**: CU-CP and CU-UP didn't agree at startup — check
  capabilities, supported S-NSSAIs.

## Parsing script

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/extract_proc_codes.py <e1ap.pcap> --proto e1ap
python3 ${CLAUDE_SKILL_DIR}/references/scripts/correlate_run.py <run-dir> --protocols e1ap
```

## Accumulated knowledge

*Append: GTP-U TEID handling quirks, CU-UP-initiated release patterns,
multi-DRB bearer surprises.*

- 2026-05-26 — Per-UE E1AP IDs are exposed in tshark 4.4.7 as
  `e1ap.GNB_CU_CP_UE_E1AP_ID` / `e1ap.GNB_CU_UP_UE_E1AP_ID` (uppercase G).
  The lowercase `e1ap.gNB_*` variants exist in the dissector but are not
  populated for the IEs in OCUDU pcaps. Same caveat applies to F1AP.
- 2026-05-26 — Procedure codes in the OCUDU build verified against an
  inter-RU HO capture: bearerContextSetup=8, bearerContextModification=9,
  bearerContextRelease=11 (not 1/2/4 as initially documented).
