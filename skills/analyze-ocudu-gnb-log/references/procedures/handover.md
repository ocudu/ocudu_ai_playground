# Procedure: Handover

NR handovers come in two flavours in OCUDU runs:

- **Intra-gNB / inter-cell within the same DU** — the source and target cells
  are both managed by the same gNB. The HO command is delivered as an
  `rrcReconfiguration` whose body contains the `reconfigurationWithSync` IE
  (with the target cell's pci, RACH config, and security key chain info).
  No NGAP traffic is involved.
- **Inter-gNB (XnAP or NGAP-based)** — visible as NGAP `HandoverRequired` /
  `HandoverRequest` / `HandoverCommand` / `HandoverNotify` on the gNB log,
  plus an Xn association if XnAP is used.

In the Retina test catalogue:
- `mobility.intra_ru_ho.key_regen` — intra-gNB HO between cells served by the
  same RU.
- `mobility.inter_ru_ho.cfra_ho` — intra-gNB HO between cells on different RUs
  (still same gNB), exercising Contention-Free Random Access on the target.
- `mobility.reestablishment.intra_ru` — RLF + RRC reestablishment (see
  `reestablishment.md`).

These three tests typically have `rrc_level: warning` and `cu_level: warning`,
so the HO command itself **does not appear** in `gnb.log`. The visible signals
are at the scheduler/MAC level. To see the HO command body, enable
`f1ap.pcap` (already enabled in these tests) and use the `analyze-pcap` skill.

## Expected sequence — intra-gNB inter-cell HO (info-level RRC enabled)

| Step | Layer | Log line |
|---|---|---|
| 1 | CU-CP | `ue=N: "Handover Routine" initialized` (only if implemented; older builds may not log this) |
| 2 | RRC  | `DCCH DL rrcReconfiguration` *and a continuation line containing `reconfigurationWithSync {`* |
| 3 | CU-CP-F1 | `Tx PDU ... UEContextModificationRequest` to the DU (target cell config) |
| 4 | DU-F1 | `Rx/Tx ... UEContextModificationResponse` |
| 5 | SCHED | New `prach(...)` on the target pci with the new `tc-rnti` (CFRA preamble in CFRA tests) |
| 6 | MAC  | `proc="MAC UE Reconfiguration": finished successfully` on the target pci |
| 7 | RRC  | `DCCH UL rrcReconfigurationComplete` on the target cell |
| 8 | CU-CP | `ue=N: "Handover Routine" finished successfully` |

Scheduler-only visibility (when RRC/CU layers are at warning):
- `[METRICS] events=[..., {rnti=0xN slot=N.N type=ue_reconf}, ...]` —
  a `ue_reconf` event near the handover time.
- `[SCHED] Cell creation idx=N` for both cells at startup.
- New PRACH events on the target cell after the HO command.

## Expected sequence — inter-gNB HO (source side)

| Step | Layer | Log line |
|---|---|---|
| 1 | RRC | Measurement report decoded |
| 2 | CU-CP | `"Handover Preparation Routine" initialized` |
| 3 | NGAP | `Tx PDU ue=N ran_ue=N: HandoverRequired` |
| 4 | NGAP | `Rx PDU ... HandoverCommand` |
| 5 | RRC | `DCCH DL rrcReconfiguration` (carrying the target's `reconfigurationWithSync`) |
| 6 | NGAP | `Tx PDU ... UplinkRanStatusTransfer` / `DownlinkRanStatusTransfer` |
| 7 | CU-CP | UEContextRelease after the handover completes on the target |

## Failure markers

| Marker | Likely cause |
|---|---|
| HO command sent but no `rrcReconfigurationComplete` (target side) | UE failed RACH on the target / RLF |
| `rrcReestablishmentRequest` shortly after HO command | Failed sync → falling back to reestablishment (see `reestablishment.md`) |
| `Late DL/UL HARQs` spike on the target around HO time | Target cell radio conditions / TA outdated |
| HO command never sent though `trigger_handover_from_measurements: true` and meas report received | Measurement event A3 threshold not met, or no neighbour cell config |

## Investigation checklist

1. Are RRC/CU layers visible? Check log levels:
   ```bash
   grep -E "rrc_level|cu_level" ocudu_gnb.yml
   ```
   If both are `warning`, skip directly to step 4 (pcap) — the gNB log alone
   won't show the HO command body.
2. Count handovers:
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "reconfigurationWithSync \{" --count
   ```
3. Per-UE HO timeline (info-level only):
   ```bash
   python3 ocudu_log_search.py gnb.log --pattern "Handover Routine" --max-lines 30
   ```
4. Use the F1AP/NGAP PCAP for the HO command body — handoff to `analyze-pcap`:
   - F1AP HO trace: UEContextModificationRequest with `reconfigurationWithSync`.
   - NGAP HO trace (inter-gNB): HandoverRequired / HandoverCommand.
5. If scheduler events show ue_reconf without RRC trace, infer the HO from the
   target cell's PRACH on a new pci:
   ```bash
   python3 ocudu_log_search.py gnb.log --layer SCHED --pattern "prach\(" --max-lines 30
   ```
6. Cross-correlate with the Amarisoft UE log (`analyze-amari-ue-log`) — the
   UE log makes it obvious whether the UE acquired the target cell, sent the
   reconfigComplete, or fell into RLF.

## Cross-references

- `procedures/reestablishment.md` — HO failure usually surfaces as a
  reestablishment.
- `analyze-pcap` skill: F1AP / NGAP / RRC handover messages.
