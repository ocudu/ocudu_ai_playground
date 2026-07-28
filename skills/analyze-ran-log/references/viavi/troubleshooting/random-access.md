# Troubleshooting: random access (VIAVI)

Failure playbook for clustered RA errors. For the RA line shapes and counting
(the expected-sequence / vocabulary view), see `../reference/random-access.md`.

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

## Cross-references

- ../reference/random-access.md
