# Procedure: PDU session / DRB setup

The PDU session is set up as part of Initial Context Setup (see
`ue-attach.md`): the AMF sends the PDU session list in
`InitialContextSetupRequest`, the gNB requests the bearer from the CU-UP
over E1AP, then plumbs the DRBs to the DU over F1AP and acknowledges with
`PDUSessionResourceSetupResponseTransfer`.

For attaches that **succeeded** at the RRC level but show **no data flow**,
this is the procedure to inspect.

## Expected sequence

| Step | Layer | Log line |
|---|---|---|
| 1 | NGAP | `Rx PDU ... InitialContextSetupRequest` (contains PDU session list) |
| 2 | CU-CP-E1 | `Tx PDU ... BearerContextSetupRequest` |
| 3 | CU-UP-E1 | `Rx PDU ... BearerContextSetupRequest` |
| 4 | CU-UP | `ue=N: PDU session psi=N attached, dl_teid=..., ul_teid=...` |
| 5 | CU-UP-E1 | `Tx PDU ... BearerContextSetupResponse` |
| 6 | CU-CP-E1 | `Rx PDU ... BearerContextSetupResponse` |
| 7 | CU-CP-F1 | `Tx PDU ... UEContextSetupRequest` *(if not already done as part of attach)* |
| 8 | CU-CP-E1 | `Tx PDU ... BearerContextModificationRequest` (with DRB DL/UL teids) |
| 9 | CU-UP-E1 | `Tx PDU ... BearerContextModificationResponse` |
| 10 | CU-UP | `Attaching dl_teid=... to F1-U tunnel with ul_teid=...` |
| 11 | RRC  | `DCCH DL rrcReconfiguration` (carries DRB config, RLC bearer config, PDCP) |
| 12 | RRC  | `DCCH UL rrcReconfigurationComplete` |
| 13 | GTPU | `Tunnel added. teid=0xNNNNNN` (one per direction) |

After step 13 the user-plane is up. The first DL packet from the core appears
as `[GTPU] [I] ue=N DL teid=0x...: RX SDU. sdu_len=N qos_flow=QFI=N`.

## Failure markers

| Where it fails | Marker | Likely cause |
|---|---|---|
| Step 5 missing | `BearerContextSetupRequest` not acknowledged | CU-UP not started or rejected the bearer (check `[CU-UP   ]` lines) |
| Step 5 ack with failure cause | `BearerContextSetupResponse` body shows failed bearers | QoS / DRB ID conflict — check PCAP for cause IE |
| Step 9 missing | DRB modification stalls | F1-U tunnel attach failed on DU |
| Step 13 missing despite reconfigComplete | `Tunnel added` not seen | GTPU layer at warning, or tunnel creation actually failed |
| Step 12 received but no UL data | `[GTPU] [I] UL teid=...: TX PDU` lines absent | UE not generating traffic, or NAS PDU session not activated on UE side |

## Investigation checklist

1. Did the bearer context come up?
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "BearerContext(Setup|Modification)(Request|Response)" --max-lines 40
   ```
2. Did the F1-U tunnel attach?
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "Attaching dl_teid|F1-U tunnel" --max-lines 20
   ```
3. Is the user-plane flowing?
   ```bash
   python3 ocudu_log_search.py gnb.log --layer GTPU --max-lines 30
   ```
4. Did the reconfiguration land?
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "rrcReconfiguration(Complete)?" --max-lines 30
   ```
5. If E1AP layer is at warning, enable `e1ap_level: info` in `ocudu_gnb.yml`
   for the next run, or analyse the `e1ap.pcap` via `analyze-pcap`.

## Cross-references

- `procedures/ue-attach.md` — bearer setup overlaps with the attach
  procedure.
- `analyze-pcap` skill: `e1ap.pcap`, `f1ap.pcap` carry the full IE bodies.
