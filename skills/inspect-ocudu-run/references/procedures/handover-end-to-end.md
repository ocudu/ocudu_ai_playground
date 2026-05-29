# Handover, end to end (cross-artifact trace)

Correlate a handover across the UE log (cell switch + target RACH), the gNB log
(reconfig-with-sync + target-cell scheduling), and the F1AP/NGAP pcaps. The UE
keeps its Amarisoft UEID throughout — use it as the anchor; the C-RNTI changes on
the target cell.

## Sequence and join keys

| Step | UE log | gNB log | pcap | Join key |
|---|---|---|---|---|
| HO decision | — | `[CU-CP] Trigger ... handover` (info level) | — | CU `ue=` |
| HO command | `[RRC]` reconfiguration received | `[RRC] DCCH DL rrcReconfiguration` whose body has `reconfigurationWithSync` | `f1ap` UEContextModificationRequest | CU `ue=` ↔ `du_ue` (map_ue_ids) |
| Target RACH | `[PHY] UL <ueid> <newCC> <tc-rnti> <slot> PRACH:` (CC switches to target) | `[PHY] [<slot>] PRACH:` on target pci → `[SCHED] prach(... tc-rnti=0xT2)` on target | — | wall-clock occasion → **tc-rnti T2** |
| Target Msg3/recfg | `[PHY] UL ... <T2> PUSCH` then reconfigurationComplete | `[RRC] DCCH UL rrcReconfigurationComplete` (target cell) | `f1ap` UEContextModificationResponse | **(SFN.slot, T2)** exact |
| Inter-gNB only | — | `[NGAP] HandoverRequired/HandoverCommand` | `ngap` Handover* | `ran_ue` ↔ `amf_ue` |

Amarisoft cell index `CC` switching from source to target in `ue.log` is the
UE-side proof the cell change happened. The new C-RNTI on the target appears in
both the UE PHY lines and the gNB target-cell scheduling.

## Important: log level often hides the gNB HO command

Mobility tests frequently run `rrc_level: warning` / `cu_level: warning`, so the
`reconfigurationWithSync` body and the `Trigger handover` lines are **absent**
from `gnb.log`. In that case:
- Read the HO command from the **F1AP pcap** (`analyze-pcap`):
  `UEContextModificationRequest` carrying `reconfigurationWithSync`.
- Confirm the cell switch from the **UE log** (`analyze-amari-ue-log`): the `CC`
  index change and the target-cell PRACH.
- Confirm target-cell access in `gnb.log` scheduler events (PRACH on the target
  pci with a new tc-rnti).

## How to drive it

```bash
# UE side: did the UE switch cells and RACH on the target?
#   delegate to analyze-amari-ue-log (CC change, PRACH on target)
# gNB side: HO command + target scheduling
#   delegate to analyze-ocudu-gnb-log; if RRC at warning, use the F1AP pcap:
python3 ${CLAUDE_SKILL_DIR}/references/scripts/map_ue_ids.py f1ap.pcap | grep -E "UEContextModification|Handover"
# Radio on the target cell for the new C-RNTI:
python3 ${CLAUDE_SKILL_DIR}/references/scripts/correlate_radio.py <run-dir> --kind pusch --rnti 0x<T2>
```

## Failure attribution

| Symptom | Cross-source signal | Side |
|---|---|---|
| HO command sent, UE never RACHes target | F1AP has UEContextModificationRequest; UE log shows no target PRACH / no CC switch | UE / radio on target |
| UE RACHes target, no reconfigurationComplete | target PRACH present; gNB has no UL rrcReconfigurationComplete | target-cell decode; correlate Msg3 PUSCH |
| Reestablishment right after HO | `rrcReestablishmentRequest` follows the HO command | HO failure → see `radio-link-failure.md` |
| Inter-gNB HO expected but no NGAP Handover* | `ngap.pcap` lacks HandoverRequired | it was intra-gNB, or HO never triggered |
