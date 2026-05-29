# Cross-protocol identifiers

OCUDU pcaps use several UE identifier types depending on the protocol. This
file is the reference table; per-protocol detail lives in
`ngap.md`, `f1ap.md`, `e1ap.md`, `mac.md`, `rlc.md`.

## Identifier table

| Identifier | tshark field | Assigned by | Scope | Survives HO? | Survives re-establishment? |
|---|---|---|---|---|---|
| C-RNTI | `mac-nr.rnti`, `f1ap.C_RNTI` | gNB scheduler | One cell, one UE-connection | No (re-issued on target) | Usually no |
| `gNB-DU-UE-F1AP-ID` | `f1ap.GNB_DU_UE_F1AP_ID` | DU | One DU, one UE | No (target DU reissues) | Re-issued |
| `gNB-CU-UE-F1AP-ID` | `f1ap.GNB_CU_UE_F1AP_ID` | CU | One CU, one UE | Yes (intra-CU HO) | Yes |
| `RAN-UE-NGAP-ID` | `ngap.RAN_UE_NGAP_ID` | gNB | One NG association | Yes | Yes |
| `AMF-UE-NGAP-ID` | `ngap.AMF_UE_NGAP_ID` | AMF | One AMF | Yes | Yes |
| `gNB-CU-CP-UE-E1AP-ID` | `e1ap.GNB_CU_CP_UE_E1AP_ID` | CU-CP | One E1 association | Yes | Yes |
| `gNB-CU-UP-UE-E1AP-ID` | `e1ap.GNB_CU_UP_UE_E1AP_ID` | CU-UP | One E1 association | Yes | Yes |

## Time base

All identifiers above are local to a single NG/F1/E1 association. RAN-UE-NGAP-ID
restarts at 1 when the gNB reconnects to an AMF. Treat IDs as keys *within one
run directory*; do not assume continuity across runs.

## Joining across protocols

Each protocol has its own per-UE identity script:

- `f1ap_ue_ids.py <f1ap.pcap>` — F1AP UEs (cu_ue_f1ap_id, du_ue_f1ap_ids, C-RNTIs)
- `ngap_ue_ids.py <ngap.pcap>` — NGAP UEs (ran_ue_ngap_id, amf_ue_ngap_id)
- `e1ap_ue_ids.py <e1ap.pcap>` — E1AP UEs (e1_cp_ue_id, e1_up_ue_id)

Each script clusters by direct ID equality within its own protocol. Joining
*across* protocols uses temporal adjacency at registration (F1AP InitialULRRC
≈ NGAP InitialUEMessage, within 50 ms) and at PDU-session setup (NGAP
PDUSessionResourceSetup ≈ E1AP BearerContextSetup, within a few hundred ms).
For an event-level cross-protocol timeline, use `correlate_run.py`.

## Wall-clock alignment

`frame.time_epoch` is comparable across all 5 sibling pcaps (µs precision).
There is no per-protocol clock skew.
