# Procedure: RRC reestablishment (post-RLF recovery)

When the UE detects Radio Link Failure (RLF) — too many consecutive PDCCH out-
of-sync indications, T310 expiry, RACH max attempts, integrity check failure,
or HO failure — it tears down the dedicated RRC connection and attempts to
restore it on the same or a neighbour cell via the RRC Reestablishment
procedure.

On the gNB side this means a UE arrives with a `rrcReestablishmentRequest`
carrying the previous c-rnti and pci so the gNB can locate the old UE
context.

## Expected sequence

| Step | Layer | Log line |
|---|---|---|
| 1 | SCHED | New `prach(... tc-rnti=0xNNNN)` from the (returning) UE |
| 2 | MAC  | `proc="MAC UE Creation": finished successfully` for the new tc-rnti |
| 3 | CU-CP-F1 | `Rx PDU ... InitialULRRCMessageTransfer` |
| 4 | RRC  | `CCCH UL rrcReestablishmentRequest` (carries old c-rnti, old pci, reestablishmentCause) |
| 5 | CU-CP | UE context lookup — old `ue=N_old` matched to new c-rnti |
| 6 | RRC  | `CCCH DL rrcReestablishment` |
| 7 | RRC  | `DCCH UL rrcReestablishmentComplete` |
| 8 | RRC  | `DCCH DL rrcReconfiguration` (re-applies DRB/SRB config) |
| 9 | RRC  | `DCCH UL rrcReconfigurationComplete` |

If the gNB cannot find the old UE context (e.g. it timed out, or different
gNB ID), it falls back to a full RRC Setup:
- `RRC reject` or `RRC setup` instead of `RRC reestablishment` at step 6.
- In `cu_cp.rrc.force_reestablishment_fallback: true` mode, the gNB always
  falls back.

## Failure markers

| Marker | Meaning |
|---|---|
| `CCCH DL rrcReject` after a reestablishment request | gNB refused to reestablish (max ue, mismatched IDs) |
| `CCCH DL rrcSetup` after a reestablishment request | Fallback to full setup — UE context was lost |
| `Reestablishment failed` log line (if present in the build) | Internal failure |
| No `rrcReestablishmentComplete` after `rrcReestablishment` | UE didn't ACK — likely radio gone |

## Investigation checklist

1. Find every reestablishment attempt:
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "rrcReestablishment" --max-lines 30
   ```
2. For each, capture the cause carried in the request body. The cause
   appears as a continuation line under `rrcReestablishmentRequest`:
   - `reconfigurationFailure` — HO command failed → see `handover.md`.
   - `handoverFailure` — explicit HO failure.
   - `otherFailure` — generic RLF (PDCCH out-of-sync, T310, RACH max).
3. Match old → new c-rnti via `CU-CP` log lines, then trace the original UE
   to see what happened just before:
   ```bash
   python3 ocudu_log_search.py gnb.log --rnti <old_hex> --before <reest_ts> --max-lines 80
   ```
4. PHY/MAC view of the radio link in the seconds before the reestablishment:
   ```bash
   python3 ocudu_log_search.py gnb.log --layer PHY --rnti <old_hex> \
       --after <T-2s> --before <reest_ts> --pattern "crc=FAIL|sr=yes" --max-lines 30
   ```
5. Cross-correlate with the Amarisoft UE log — the UE log emits
   `rrc_reestablishment` SIM-Event or an internal RLF notification.

## Cross-references

- `procedures/handover.md` — most reestablishments in mobility tests follow a
  failed HO.
- `procedures/phy-issues.md` — PHY-side radio link degradation that triggers
  RLF.
