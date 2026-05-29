# Attach, end to end (cross-artifact trace)

Follow one UE's initial attach across the UE log, the gNB log, and the pcaps,
naming the join key at each hop. Per-side detail lives in the sub-skills; this is
the correlation spine.

## Sequence and join keys

| Step | UE log (`ue.log`) | gNB log (`gnb.log`) | pcap | Join key |
|---|---|---|---|---|
| PRACH | `[PHY] UL <ueid> 00 - <slot> PRACH: sequence_index=K` | `[PHY] [<slot>] PRACH: detected_preambles=[{idx=J ...}]` → `[SCHED] prach(ra-rnti=.. preamble=J tc-rnti=0xT)` | — | wall-clock occasion (NOT index: K≠J); then **tc-rnti** |
| Msg2 RAR | `[MAC] DL - 00 RAR: rapid=J` | `[SCHED] RAR: ra-rnti=..` | — | ra-rnti / rapid |
| Msg3 PUSCH | `[PHY] UL <ueid> 00 <tc-rnti> <slot> PUSCH: ... tb_len=11` | `[PHY] [<slot>] PUSCH: rnti=0xT ... tbs=11 crc=OK` | — | **(SFN.slot, RNTI)** exact |
| RRC Setup | `[RRC] ... rrcSetup / rrcSetupComplete` | `[RRC] CCCH UL rrcSetupRequest → CCCH DL rrcSetup → DCCH UL rrcSetupComplete` | `f1ap` InitialULRRCMessageTransfer | C-RNTI ↔ `du_ue`/`cu_ue` (map_ue_ids) |
| NAS / NGAP | `[NAS] UL <ueid> 5GMM: Registration request` (5GC side in `mme.log`) | `[NGAP] Tx PDU ue=N ran_ue=N: InitialUEMessage` → `Rx ... amf_ue=M` | `ngap` InitialUEMessage | `ran_ue` ↔ `amf_ue`; 5GC NAS UEID = `amf_ue` (hex) |
| Security + caps | — | `[RRC] securityModeCommand/Complete`, `ueCapabilityEnquiry/Information` | `f1ap` DL/UL RRC transfer | C-RNTI |
| ICS + bearer | `[PHY]` DRB traffic begins | `[CU-CP] "Initial Context Setup Routine" finished`; `[CU-CP-E1] BearerContextSetup` | `e1ap` BearerContextSetup; `ngap` ICSResponse | `cu_cp_ue` ↔ `cu_up_ue` |

## How to drive it

1. Pick the UE: Amarisoft UEID (UE log) or C-RNTI. Use `ue-identity-map.md` to
   get the rest of the chain (`map_ue_ids.py` on the pcaps).
2. Confirm Msg3 reached the gNB:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/references/scripts/correlate_radio.py <run-dir> --kind prach
   python3 ${CLAUDE_SKILL_DIR}/references/scripts/correlate_radio.py <run-dir> --kind pusch --rnti 0x<tc-rnti>
   ```
3. For RRC/NGAP/E1AP detail, delegate to `analyze-ocudu-gnb-log` (gNB side) and
   `analyze-pcap` (the F1AP/NGAP/E1AP bodies); for the UE's view delegate to
   `analyze-amari-ue-log`.

## Where attach breaks, and who to blame

| Symptom | Cross-source signal | Likely side |
|---|---|---|
| No gNB PRACH detection for a UE PRACH | UE has `PRACH:` lines, gNB PHY has none at that occasion | UE TX power / PRACH config / RU; check `analyze-amari-ue-log` + `analyze-ocudu-gnb-log` |
| Msg3 `crc=KO` but UE transmitted | `correlate_radio --kind pusch` → `rx-ko/ue-tx` | gNB decode / ZMQ alignment / contention |
| Msg3 `crc=KO sinr=inf`, no UE TX | `rx-ko/ue-silent` | UE DTX — UE never sent Msg3 |
| RRC stops after setup, no NGAP InitialUEMessage | gNB has rrcSetupComplete but NGAP pcap lacks InitialUEMessage | gNB↔AMF (NGAP) — delegate to `analyze-pcap` |
| InitialUEMessage but no ICS | NGAP has no InitialContextSetupRequest back | 5GC — check `mme.log` (light-touch) |
| RACH contention (multi-UE) | `ue-extra-tx/contention` rows | expected; not a fault |
