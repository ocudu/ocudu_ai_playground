# F1AP — CU ↔ DU (F1-C interface)

## Purpose

F1AP carries the control plane between the gNB-CU and gNB-DU in a split
deployment. The `f1ap.pcap` captures UE-context lifecycle messages, F1
infrastructure messages (F1 Setup, gNB-CU/DU Configuration Update), and the
RRC-container transfers between CU and DU.

## Key tshark filters

```bash
# All F1AP messages with UE IDs
tshark -r f1ap.pcap \
    -T fields -E separator=$'\t' \
    -e frame.number -e frame.time_epoch \
    -e f1ap.procedureCode \
    -e f1ap.GNB_DU_UE_F1AP_ID -e f1ap.GNB_CU_UE_F1AP_ID

# UE context lifecycle
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 5 || f1ap.procedureCode == 6 || f1ap.procedureCode == 7'

# RRC container traffic (UL/DL RRC message transfer)
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 11 || f1ap.procedureCode == 12 || f1ap.procedureCode == 13'

# Specific procedures
tshark -r f1ap.pcap -Y 'f1ap.procedureCode ==  1'   # F1Setup
tshark -r f1ap.pcap -Y 'f1ap.procedureCode ==  5'   # UEContextSetup
tshark -r f1ap.pcap -Y 'f1ap.procedureCode ==  6'   # UEContextRelease
tshark -r f1ap.pcap -Y 'f1ap.procedureCode ==  7'   # UEContextModification
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 11'   # InitialULRRCMessageTransfer
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 12'   # DLRRCMessageTransfer
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 13'   # ULRRCMessageTransfer
```

## Identifier mapping

- `f1ap.GNB_DU_UE_F1AP_ID` — DU-assigned, present from InitialULRRCMessageTransfer.
- `f1ap.GNB_CU_UE_F1AP_ID` — CU-assigned, present once UEContextSetupRequest
  has been sent.
- `f1ap.C_RNTI` — present in InitialULRRCMessageTransfer (the DU's C-RNTI for
  this UE). Note the field name uses an underscore and capital `C` — the
  natural-looking `f1ap.cRNTI` is **not** a valid tshark field.
- See `../cross-pcap-correlation.md` for joining to NGAP / E1AP.

## UE arrival paths in f1ap.pcap

A UE shows up in `f1ap.pcap` via one of two first-message paths, depending on
*how* it arrived on this DU:

| First F1AP message | What it means | DU role |
|---|---|---|
| `InitialULRRCMessageTransfer` (proc 11) | UE attached via RACH on this cell. The DU has just allocated a C-RNTI; the CU has not yet assigned a `gNB-CU-UE-F1AP-ID`. | Source/only DU. |
| `UEContextSetup` (proc 5) — Request from CU | UE was handed over to this DU from elsewhere under the same CU. No preceding RACH on this DU; the C-RNTI in the request is freshly allocated for the target cell. | Target DU. |

In a handover test, the first-F1AP-message variation across UEs is the
*expected* signature, not an anomaly. See
[`../procedures/handover.md`](../procedures/handover.md) for the full target-DU
sequence.

## Common procedures and codes

Verified against an OCUDU `f1ap.pcap` capture:

| Code | Procedure | Initiator | Notes |
|---:|---|---|---|
|  1 | F1Setup | DU | at link establishment |
|  5 | UEContextSetup | CU | new UE on DU |
|  6 | UEContextRelease | CU | end of UE on DU |
|  7 | UEContextModification | CU | bearer/cell change |
| 11 | InitialULRRCMessageTransfer | DU | first RRC message from UE |
| 12 | DLRRCMessageTransfer | CU | CU RRC → UE |
| 13 | ULRRCMessageTransfer | DU | UE RRC → CU |

## Common failure signatures

- **UEContextSetupFailure**: DU can't accept the UE — typically because no
  C-RNTI is available, cell isn't admitting UEs, or the requested DRBs
  conflict.
- **UEContextReleaseCommand with `radio-connection-with-ue-lost`**: DU
  reported the UE as lost; usually triggered by MAC inactivity timer or RLF.
- **No UEContextSetupResponse for a sent Request**: CU side issue or DU
  crash; check the gNB log around the matching epoch.
- **InitialULRRCMessageTransfer without subsequent UEContextSetupRequest**:
  CU received the UE but isn't deciding to admit it — usually a CU-CP
  routing or AMF-selection issue.

## Parsing script

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/extract_proc_codes.py <f1ap.pcap> --proto f1ap
python3 ${CLAUDE_SKILL_DIR}/references/scripts/correlate_run.py <run-dir> --protocols f1ap
```

## Accumulated knowledge

- 2026-05-26 — tshark 4.4.7 field name for the per-UE C-RNTI carried in
  InitialULRRCMessageTransfer is `f1ap.C_RNTI` (capital `C`, underscore). The
  natural-looking `f1ap.cRNTI` is **not** a valid field — using it makes
  tshark exit 1 with "Some fields aren't valid".
- 2026-05-26 — F1AP procedure codes in the OCUDU build differ from the
  initial documentation: InitialULRRCMessageTransfer is 11 (not 12),
  DLRRCMessageTransfer is 12 (not 16), ULRRCMessageTransfer is 13 (not 15).
