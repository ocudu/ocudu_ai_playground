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
  this UE).
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
| 26 | F1Removal | DU or CU | tear down the F1 interface |

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
- **InitialULRRCMessageTransfer with an *empty* DUtoCURRCContainer**: the DU
  could not allocate the UE's dedicated resources (commonly the cell PUCCH
  resource pool — `nof_cell_sr_resources`/`nof_cell_csi_resources`) and signals
  "can't serve this UE" per TS 38.473 §8.4.1.2. The CU then **rejects** the UE:
  it sends a `UEContextReleaseCommand` carrying an `rrcReject` (with a wait
  timer) as an `RRCContainer` on `SRBID=0`. The IE is *present but zero-length*
  in this case, so detect it by container **content length**, not by presence:
  `-T fields -e f1ap.DUtoCURRCContainer` → empty value ⇒ "can't serve" (a
  non-empty value carries the CellGroupConfig for an admitted UE).

## RRC PDUs inside F1AP containers are NOT auto-dissected (tshark gotcha)

tshark dissects the RRC PDU carried in the RRC **message-transfer** procedures
(`InitialULRRCMessageTransfer`, `DL/ULRRCMessageTransfer`) and in
`UEContextSetup`/`Modification` — for those, `nr-rrc.<type>_element` fields fire.
But it does **not** dissect the `RRCContainer` inside a `UEContextReleaseCommand`
(proc 6): it prints that container as raw hex. So `tshark -V | grep -E
'rrcReject|rrcSetup|rrcRelease'` and filters like `nr-rrc.rrcReject_element` give
**false negatives** for the release-command case — the RRC message name never
appears even though it is present. Decode the `f1ap.RRCContainer` hex yourself
there; `SRBID` picks the channel (`SRBID=0` → CCCH, `SRBID≥1` → DCCH). A
security-activated DCCH release (`rrcRelease`) is PDCP-protected, so its bytes
are opaque; a `SRBID=0` CCCH container is a plain `rrcReject`/`rrcSetup`.

```bash
# List the RRC containers actually being sent (decode the hex, don't grep -V)
tshark -r f1ap.pcap -Y 'f1ap.procedureCode==6 && f1ap.RRCContainer' \
    -T fields -e f1ap.RRCContainer | sort | uniq -c
```

Quick manual PER decode of a DL-CCCH message: bit0 = `message` choice (0=`c1`),
bits1–2 = `c1` choice (`00`=`rrcReject`, `01`=`rrcSetup`). Example: an admission
reject appears as `UEContextReleaseCommand`, `SRBID=0`, `RRCContainer: 09e0` →
`c1: rrcReject`, `waitTime=16s` — completely invisible to `grep rrcReject`.
Distinguish reject-in-release from a normal release by the container: a bare
release has no `RRCContainer`; a reject carries the short CCCH `rrcReject`.

## Parsing scripts

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/extract_proc_codes.py <f1ap.pcap> --proto f1ap
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/correlate_run.py <run-dir> --protocols f1ap

# Per-UE F1AP identity table (one row per UE)
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/f1ap_ue_ids.py <f1ap.pcap>

# Per-message F1AP timeline with decoded RRC + NAS message types (one row per
# message): frame, first_iso, message, rrc, nas, cu/du F1AP IDs, C-RNTI.
# Resolves the RRC type from tshark's dissection and hand-decodes the CCCH
# container (rrcReject/rrcSetup) that tshark leaves as hex in a release command.
# NAS type is named from tshark's decode (ciphered post-security NAS shows '-').
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/f1ap_messages.py <f1ap.pcap>
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/f1ap_messages.py <f1ap.pcap> --ue 640   # one UE end-to-end
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/f1ap_messages.py <f1ap.pcap> --nas      # only NAS-bearing msgs
```
