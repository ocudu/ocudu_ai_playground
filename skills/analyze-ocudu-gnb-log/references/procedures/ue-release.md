# Procedure: UE release

UE release happens when the AMF (or, in some configurations, the gNB itself
after the inactivity timer) decides the RRC connection should be torn down.
The trigger arrives as NGAP `UEContextReleaseCommand`, propagates down
through E1AP (bearer release) and F1AP (UE context release), and ends with
the DU clearing its UE state and the CU-CP acknowledging back to the AMF.

## Expected sequence

| Step | Layer | Log line |
|---|---|---|
| 1 | NGAP | `Rx PDU ... UEContextReleaseCommand` (carries `cause` IE) |
| 2 | RRC  | `DCCH DL rrcRelease` |
| 3 | CU-CP-E1 | `Tx PDU ... BearerContextReleaseCommand` |
| 4 | CU-UP-E1 | `Rx PDU ... BearerContextReleaseCommand` |
| 5 | CU-UP | `ue=N: Disconnecting PDU session with psi=N` |
| 6 | CU-UP-E1 | `Tx PDU ... BearerContextReleaseComplete` |
| 7 | CU-CP-E1 | `Rx PDU ... BearerContextReleaseComplete` |
| 8 | CU-CP-F1 | `Tx PDU ... UEContextReleaseCommand` |
| 9 | DU-F1 | `Rx PDU ... UEContextReleaseCommand` |
| 10 | DU-MNG | `ue=N: DRB traffic stopped` |
| 11 | DU-F1 | `proc="UE Context Release": RRC container not ACKed within a time window of 120msec.` *(common in simulated runs — the UE doesn't ack the DL because the test ends; benign)* |
| 12 | DU-MNG | `ue=N proc="UE Delete": Procedure started....` |
| 13 | DU-MNG | `ue=N: SRB and DRB traffic stopped` |
| 14 | DU-F1 | `ue=N c-rnti=0xNNNN ... F1 UE context removed.` |
| 15 | DU-MNG | `ue=N proc="UE Delete": Procedure finished successfully.` |
| 16 | DU-F1 | `Tx PDU ... UEContextReleaseComplete` |
| 17 | CU-CP-F1 | `Rx PDU ... UEContextReleaseComplete` |
| 18 | CU-CP | `ue=N: "UE Removal Routine" finished successfully` |
| 19 | NGAP | `Tx PDU ran_ue=N amf_ue=N: UEContextReleaseComplete` |

After step 19 the AMF considers the UE released. The gNB context for `ue=N`
no longer exists; if the same UE re-attaches it will get a new `ue=N` index.

## Failure markers

| Marker | Meaning |
|---|---|
| Release triggered by gNB inactivity (`Inactivity timer expired`) | Normal in idle tests — UE was attached but didn't generate traffic for `cu_cp.inactivity_timer` seconds |
| `BearerContextReleaseComplete` missing | CU-UP didn't ack — process stuck (check `[CU-UP   ]` lines) |
| `"UE Removal Routine" finished successfully` missing despite step 1 happening | Release got stuck mid-flow; CU-CP context leak — check warnings for F1/E1 timeouts |
| `RRC container not ACKed within a time window of 120msec` | Benign in simulator runs (the UE may have already detached); becomes a concern on real radios if persistent |

## Investigation checklist

1. Find release triggers:
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "UEContextReleaseCommand" --max-lines 20
   ```
2. Match each command to its completion:
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "UE Removal Routine.*finished" --count
   ```
3. Was the cause IE in the command an error? The cause is carried in the
   NGAP body — visible in `ngap.pcap` (handoff to `analyze-pcap`), or in
   `gnb.log` only when `ngap_level: info` and `hex_max_size > 0`.
4. For UEs that never released (creations > releases), find the missing UE:
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "UE created" --max-lines 50
   python3 ocudu_log_search.py gnb.log --pattern '"UE Removal Routine" finished' --max-lines 50
   ```

## Cross-references

- `procedures/ue-attach.md` — release reverses the attach.
- `analyze-pcap` skill: `ngap.pcap` carries the `cause` IE in
  `UEContextReleaseCommand`.
