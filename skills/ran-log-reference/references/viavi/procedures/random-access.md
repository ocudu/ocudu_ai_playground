# Procedure: random access (VIAVI)

Random access is the most common VIAVI failure signal and the entry point for
most attach/mobility problems. Every PRACH attempt is an `I: CMPI L2 Random
Access …` line keyed by `UE Id:<N>`.

## Line shapes

```
L2 Random Access Initiated :UE Id:N (<trigger>: Cell Id C, Dl Freq F, SSB Id S)
L2 Random Access Complete  :UE Id:N (TC-RNTI: 0xXXXX, TimingAdv: T, PreambleTxCount: P)
L2 Random Access Error     :UE Id:N (Result: <reason>, TC-RNTI: -, TimingAdv: -, PreambleTxCount: P)
L2 Random Access Cancelled :UE Id:N (…)
```

`<trigger>` tells you *why* the UE did RA:

| Trigger | Cause |
|---|---|
| `Connection Establish` | Initial / idle-to-connected access |
| `Handover` | Contention-free RA onto a target cell |
| `SR MAX Exceeded` | Scheduling-request retries exhausted → RA fallback |
| `SR NO Resource` | No SR resource configured → RA fallback |

`PreambleTxCount` = preambles sent before success/failure (1 = first-shot
success; high values = poor coverage / contention). An **Error** is typically
followed immediately by `RRC RRC Connection Re-establishment Started` for the
same UE.

## Counting

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/viavi/viavi_log_summary.py <log>   # RA section
# or by hand:
for k in Initiated Complete Error Cancelled; do \
  echo -n "$k "; LC_ALL=C grep -ac "Random Access $k" "$log"; done
```

Initiated vs Complete vs Error do **not** reconcile to a single arithmetic
identity across the run — a UE can be Initiated in one window and Complete/Error
in another, and an attempt may be Cancelled. Read them as rates, not a balance.

## Failure markers & causes

| `Result:` reason | Likely cause |
|---|---|
| `Max_Preambles_Exceeded` | UE sent all preambles without a RAR — no/late Msg2 from the gNB, weak UL, or PRACH config mismatch |

When RA errors cluster, check:

1. **Trigger mix** — `Handover` vs `Connection Establish` errors point at different
   subsystems (mobility config vs initial access).
   `--event "Random Access Initiated"` and inspect the trigger.
2. **Which UEs / cells** — scope `--ue N` or grep the `Cell Id`; a single-cell
   cluster suggests a per-cell PRACH/coverage issue.
3. **`PreambleTxCount` distribution** — consistently high counts (even on
   *Complete*) indicate marginal UL before any hard failure.
4. **Network side** — RA is a two-sided procedure; confirm against the **OCUDU
   gNB log** (PRACH detection, RAR/Msg2 scheduling) and the **MAC pcap**. The
   VIAVI log only shows the tester's view.
