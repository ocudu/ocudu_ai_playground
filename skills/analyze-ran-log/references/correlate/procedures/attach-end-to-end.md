# Attach, end to end (cross-artifact trace)

Follow one UE's initial attach across the UE log, the gNB log, and the pcaps,
naming the join key at each hop. Per-side detail lives in the per-type subtrees
(`../../pcap/`, `../../ocudu/`, `../../amari-ue/`); this is the correlation spine.

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

## 2-step RA (MsgA/MsgB) notes

If PRACH/Msg3 rows above don't match (the run uses `two_step_rach`/`msgA`/`msgB`
config), see `../../common/procedures/random-access.md` § 2-step RA type for the
message ladder and the MAC PDU formats. Cross-artifact join keys:

| Step | UE log (`ue.log`) | gNB log (`gnb.log`) | Join key |
|---|---|---|---|
| MsgA | `[PHY] UL <ueid> 00 - <slot> PRACH: ... two_steps=1` + `[MAC] UL ... LCID:52` (CCCH) | `[SCHED] ...: MsgB: msgb-rnti=0xM ... tbs=T` (T=12 → successRAR-only, no piggybacked SDU) | msgb-rnti |
| MsgB | `[MAC] DL - 00 MSGB: uecri=0x... mac_sdu=0` (0 = no SDU, `S=0` path) + `[PHY] UL ... PUCCH format=1 ... ack=1` (UE ACKed it) | `[RRC] CCCH DL rrcSetup` logged, then a **separate** PDSCH scheduled under the new `c-rnti` (`[MAC] DL PDU: ue=N rnti=0x... size=... SDU: lcid=0`) | c-rnti (freshly assigned in the successRAR) |

**Attribution caution:** if the UE ACKs MsgB/successRAR but then shows **no**
PDCCH/PDSCH activity at all for the new C-RNTI across the gNB's retransmissions
(not just a near-miss on one slot), that is a clean one-sided signal — the gNB
transmitted, the UE never received. Before blaming the gNB's choice of MsgB
format: `S=0` (successRAR-only, `tbs=12`) is spec-legal per TS 38.321 §6.1.5a,
*not* a defect (see the ladder doc). The live hypotheses are instead: (a) the
UE/test-rig (e.g. a specific Amarisoft build — check the pinned version in the
CI job trace) fails to resume PDCCH monitoring under a freshly-applied C-RNTI
after successRAR, or (b) the gNB's search-space/CORESET config for that C-RNTI
in the immediately-following slot is wrong. Don't conclude which without
checking both.

## How to drive it

1. Pick the UE: Amarisoft UEID (UE log) or C-RNTI. Use `ue-identity-map.md` to
   get the rest of the chain (`map_ue_ids.py` on the pcaps).
2. Confirm Msg3 reached the gNB:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/correlate_radio.py <run-dir> --kind prach
   python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/correlate_radio.py <run-dir> --kind pusch --rnti 0x<tc-rnti>
   ```
3. For RRC/NGAP/E1AP detail, delegate to `ocudu` (gNB side) and
   `pcap` (the F1AP/NGAP/E1AP bodies); for the UE's view delegate to
   `amari-ue`.

## Where attach breaks, and who to blame

| Symptom | Cross-source signal | Likely side |
|---|---|---|
| No gNB PRACH detection for a UE PRACH | UE has `PRACH:` lines, gNB PHY has none at that occasion | UE TX power / PRACH config / RU; check `amari-ue` + `ocudu` |
| Msg3 `crc=KO` but UE transmitted | `correlate_radio --kind pusch` → `rx-ko/ue-tx` | gNB decode / ZMQ alignment / contention |
| Msg3 `crc=KO sinr=inf`, no UE TX | `rx-ko/ue-silent` | UE DTX — UE never sent Msg3 |
| RRC stops after setup, no NGAP InitialUEMessage | gNB has rrcSetupComplete but NGAP pcap lacks InitialUEMessage | gNB↔AMF (NGAP) — delegate to `pcap` |
| InitialUEMessage but no ICS | NGAP has no InitialContextSetupRequest back | 5GC — check `mme.log` (light-touch) |
| RACH contention (multi-UE) | `ue-extra-tx/contention` rows | expected; not a fault |
| 2-step RA: UE ACKs MsgB but follow-up C-RNTI PDSCH (RRCSetup) never received, UE `T300` expires | gNB retransmits the PDSCH (HARQ retx up to max, then discards); UE log shows zero PDCCH/PDSCH for the new C-RNTI | UE-side PDCCH-monitoring-on-new-C-RNTI bug (check UE/test-rig build) **or** gNB search-space config — not simply "the gNB used `S=0`" (see § 2-step RA notes above) |
