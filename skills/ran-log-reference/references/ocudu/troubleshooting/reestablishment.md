# Troubleshooting: RRC reestablishment (post-RLF recovery)

You see a `rrcReestablishmentRequest` — the UE hit Radio Link Failure (too many
PDCCH out-of-sync, T310 expiry, RACH max attempts, integrity failure, or HO
failure) and is trying to restore its connection. Two questions: **what caused
the RLF**, and **did recovery succeed** (vs. rejected / fell back to full setup).

For the **expected reestablishment sequence** and the fallback-to-setup variant,
see `../reference/reestablishment.md`.

## Failure markers

| Marker | Meaning |
|---|---|
| `CCCH DL rrcReject` after a reestablishment request | gNB refused to reestablish (max ue, mismatched IDs) |
| `CCCH DL rrcSetup` after a reestablishment request | Fallback to full setup — UE context was lost |
| `Reestablishment failed` log line (if present in the build) | Internal failure |
| No `rrcReestablishmentComplete` after `rrcReestablishment` | UE didn't ACK — likely radio gone; also check fallback scheduling of the DCCH grant → `ue-fallback-scheduling-issues.md` |

## Investigation checklist

1. Find every reestablishment attempt:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu/ocudu_log_search.py gnb.log --pattern "rrcReestablishment" --max-lines 30
   ```
2. For each, capture the cause carried in the request body. The cause
   appears as a continuation line under `rrcReestablishmentRequest`:
   - `reconfigurationFailure` — HO command failed → see `handover-failure.md`.
   - `handoverFailure` — explicit HO failure.
   - `otherFailure` — generic RLF (PDCCH out-of-sync, T310, RACH max).
3. Match old → new c-rnti via `CU-CP` log lines, then trace the original UE
   to see what happened just before:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu/ocudu_log_search.py gnb.log --rnti <old_hex> --before <reest_ts> --max-lines 80
   ```
4. PHY/MAC view of the radio link in the seconds before the reestablishment:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu/ocudu_log_search.py gnb.log --layer PHY --rnti <old_hex> \
       --after <T-2s> --before <reest_ts> --pattern "crc=KO|sr=yes" --max-lines 30
   ```
5. Cross-correlate with the Amarisoft UE log — the UE log emits
   `rrc_reestablishment` SIM-Event or an internal RLF notification.

## Cross-references

- `../reference/reestablishment.md` — the expected reestablishment sequence.
- `handover-failure.md` — most reestablishments in mobility tests follow a failed HO.
- `phy-issues.md` — PHY-side radio link degradation that triggers RLF.
- `ue-fallback-scheduling-issues.md` — the reestablishment DCCH grant is scheduled in fallback.
</content>
