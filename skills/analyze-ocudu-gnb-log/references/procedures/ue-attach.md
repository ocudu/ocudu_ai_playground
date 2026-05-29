# Procedure: UE attach (RRC connection + Initial Context Setup)

A UE attaches by sending PRACH → MSG3 (RRC Setup Request) → RRC Setup →
RRC Setup Complete (carries the NAS Registration Request). The NAS reaches
the AMF, security and capability exchange happen, and the AMF issues
`InitialContextSetupRequest`. The gNB then sets up the DRBs via F1AP +
E1AP and acknowledges with `InitialContextSetupResponse`.

## Expected sequence (single UE, log levels at info)

| Step | Layer | Log line |
|---|---|---|
| 1 | SCHED | `Processed slot events pci=N: prach(ra-rnti=0xN preamble=N tc-rnti=0xNNNN)` |
| 2 | SCHED | `Slot decisions pci=N ...: RAR: ra-rnti=0xN rb=[..] tbs=N` (MSG2) |
| 3 | SCHED | `Slot decisions pci=N ...: UL: ue=8192 rnti=0xNNNN ... msg3_delay=N` (MSG3 grant) |
| 4 | MAC | `UL rnti=0xNNNN subPDUs: [CCCH48: len=6, ...]` (MSG3 decoded) |
| 5 | MAC | `proc="MAC UE Creation": finished successfully` |
| 6 | MAC | `DL PDU: ue=N rnti=0xNNNN size=N: CON_RES: id=...` (MSG4 contention resolution) |
| 7 | CU-CP-F1 | `Rx PDU du=0 tid=N du_ue=N: InitialULRRCMessageTransfer` |
| 8 | CU-CP | `ue=N c-rnti=0xNNNN: UE created` |
| 9 | RRC | `CCCH UL rrcSetupRequest` |
| 10 | RRC | `CCCH DL rrcSetup` |
| 11 | RRC | `DCCH UL rrcSetupComplete` |
| 12 | NGAP | `Tx PDU ue=N ran_ue=N: InitialUEMessage` (carries NAS Registration Request) |
| 13 | NGAP | `Rx PDU ue=N ran_ue=N amf_ue=N: DownlinkNASTransport` (NAS Authentication Request) |
| 14 | RRC | `DCCH DL dlInformationTransfer` / `DCCH UL ulInformationTransfer` (NAS exchanges) |
| 15 | NGAP | `Rx PDU ... amf_ue=N: InitialContextSetupRequest` |
| 16 | CU-CP | `ue=N: "Initial Context Setup Routine" initialized` |
| 17 | SEC  | `K_gNB: ...` and derived RRC/UP keys (often blank when `hex_max_size: 0`) |
| 18 | RRC  | `DCCH DL securityModeCommand` |
| 19 | CU-CP-F1 | `Tx PDU ... UEContextSetupRequest` |
| 20 | DU-F1 | `Rx PDU ... UEContextSetupRequest` |
| 21 | DU-F1 | `Tx PDU ... UEContextSetupResponse` |
| 22 | RRC  | `DCCH UL securityModeComplete` |
| 23 | RRC  | `DCCH DL ueCapabilityEnquiry` |
| 24 | RRC  | `DCCH UL ueCapabilityInformation` |
| 25 | CU-CP-E1 | `Tx PDU ... BearerContextSetupRequest` |
| 26 | CU-UP-E1 | `Tx PDU ... BearerContextSetupResponse` |
| 27 | CU-CP-E1 | `Tx PDU ... BearerContextModificationRequest` (post-RRC-reconfig) |
| 28 | RRC  | `DCCH DL rrcReconfiguration` (carries DRB config) |
| 29 | RRC  | `DCCH UL rrcReconfigurationComplete` |
| 30 | CU-CP | `ue=N: "Initial Context Setup Routine" finished successfully` |
| 31 | NGAP | `Tx PDU ... InitialContextSetupResponse` |

After step 31 the UE is fully attached and DRBs are operational. The gNB's
`[GTPU]` lines start showing UL/DL SDUs flowing.

## Failure markers

| Where it fails | Marker | Likely cause |
|---|---|---|
| Before step 1 | PRACH not detected at all | UE TX power / SSB alignment / wrong `prach_config_index` |
| Step 1 → 6 | MSG3 doesn't decode (`crc=KO` on PUSCH for that rnti) | Power / timing / wrong MSG3 grant params |
| Step 8 missing | `Initial ULRRCMessageTransfer` arrived but `UE created` not logged | CU-CP rejected the UE — check warnings; could be max_nof_ues hit |
| Step 11 missing | `rrcSetupComplete` never seen | UE never decoded MSG4 or NAS PDU encoding failed |
| Step 15 missing | NAS exchange stalls between RRC and `InitialContextSetupRequest` | AMF auth failure (check `amf_ue` ID transition), 5GC issue |
| Step 30 missing | `"Initial Context Setup Routine"` logged `initialized` but never `finished successfully` | UE didn't reply to securityMode / Reconfiguration; or bearer setup failed in E1AP |
| Step 31 followed by immediate UEContextRelease from AMF | NAS rejected the request | Check `cause` IE in `UEContextReleaseCommand` |

## Investigation checklist

1. Did PRACH happen?
   ```bash
   python3 ocudu_log_search.py gnb.log --layer SCHED --pattern "prach\(" --count
   ```
2. Did the UE get a C-RNTI?
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "UE created" --max-lines 20
   ```
3. Did rrcSetupComplete arrive?
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "rrcSetupComplete" --max-lines 10
   ```
4. Was Initial Context Setup acknowledged?
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern '"Initial Context Setup Routine"' --max-lines 20
   ```
5. If a specific UE failed, scope everything by `c-rnti` and look at the gap:
   ```bash
   python3 ocudu_log_search.py gnb.log --rnti <hex> --max-lines 200
   ```
6. Cross-correlate with the Amarisoft UE log via `analyze-amari-ue-log` — the
   UE log shows whether the UE actually decoded MSG4, whether it sent
   Reconfiguration Complete, and whether NAS Auth Response went out.

## Multi-UE specifics

In `multiue.attach_dettach.baseline` the gNB processes UEs in batches. The
`[SCHED] [W] UE creation (ue=N): latency1=...` and
`[MAC] [W] MAC UE creation (ue=N): ...` warnings are **expected diagnostic
output**, not real warnings — they report per-UE creation latency for
performance tracking.

When `Initial Context Setup OK : K/N` shows K < N, the gap is the most
useful single signal. Find which UEs missed it:

```bash
python3 ocudu_log_search.py gnb.log --pattern "UE created" \
    | grep -oE "ue=[0-9]+" | sort -u > /tmp/created.txt
python3 ocudu_log_search.py gnb.log --pattern '"Initial Context Setup Routine" finished' \
    | grep -oE "ue=[0-9]+" | sort -u > /tmp/done.txt
comm -23 /tmp/created.txt /tmp/done.txt
```
