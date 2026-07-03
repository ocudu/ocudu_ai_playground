# Procedure: RRC reestablishment (post-RLF recovery)

Expected-sequence reference. For diagnosing an RLF / a reestablishment that was
rejected or fell back to setup, see `../troubleshooting/reestablishment.md`.

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
| 6 | RRC  | `DCCH DL rrcReestablishment` (sent on SRB1/DCCH, not CCCH) |
| 7 | RRC  | `DCCH UL rrcReestablishmentComplete` |
| 8 | RRC  | `DCCH DL rrcReconfiguration` (re-applies DRB/SRB config) |
| 9 | RRC  | `DCCH UL rrcReconfigurationComplete` |

If the gNB cannot find the old UE context (e.g. it timed out, or different
gNB ID), it falls back to a full RRC Setup:
- `RRC reject` or `RRC setup` instead of `RRC reestablishment` at step 6.
- In `cu_cp.rrc.force_reestablishment_fallback: true` mode, the gNB always
  falls back.

## Diagnosing failures

For failure markers (reject / setup-fallback / no complete) and the
investigation checklist, see `../troubleshooting/reestablishment.md`.

## Cross-references

- `handover.md` — most reestablishments in mobility tests follow a failed HO.
- `../troubleshooting/reestablishment.md` — RLF-cause + recovery diagnosis.
</content>
