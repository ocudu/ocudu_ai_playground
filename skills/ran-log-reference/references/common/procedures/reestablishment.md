# Procedure: RRC re-establishment — abstract ladder

The artifact-agnostic post-RLF recovery sequence. On Radio Link Failure (too many
PDCCH out-of-sync indications, T310 expiry, RACH max attempts, integrity failure,
or HO failure) the UE tears down its dedicated connection and tries to restore it
on the same or a neighbour cell via RRC Re-establishment, carrying the previous
C-RNTI + PCI so the gNB can find the old UE context. Spec: TS 38.331 §5.3.7 (see
`../spec-map.md`).

## Message ladder

| # | Message (abstract) | Between | Where seen |
|---:|---|---|---|
| 0 | RLF detected (T310 expiry / CRC-FAIL burst) | UE | UE log (PHY), gNB log (SCHED inactivity) |
| 1 | PRACH → RAR (returning UE, new TC-RNTI) | UE ↔ gNB | gNB log (SCHED), pcap `mac`; see `random-access.md` |
| 2 | RRC ReestablishmentRequest (CCCH; carries old C-RNTI, old PCI, cause) | UE → gNB | UE log (RRC, CCCH), gNB log (RRC), pcap `f1ap` (11, inside the RRC container) |
| 3 | UE-context lookup — old `ue=` matched to the new C-RNTI | gNB (CU-CP) | gNB log (CU-CP) |
| 4 | RRC Re-establishment (on SRB1/DCCH, **not** CCCH) | gNB → UE | UE log (RRC), gNB log (RRC), pcap `f1ap` (12) |
| 5 | RRC ReestablishmentComplete | UE → gNB | UE log (RRC), gNB log (RRC), pcap `f1ap` (13) |
| 6 | RRC Reconfiguration / Complete (re-applies SRB/DRB config) | gNB ↔ UE | UE log (RRC), gNB log (RRC) |

**Fallback:** if the gNB cannot find the old context (timed out, different gNB
ID, or `force_reestablishment_fallback: true`) it sends `rrcReject` or `rrcSetup`
at step 4 instead — forcing a full re-attach (`ue-attach.md`).

## Observation & diagnosis

How each step appears, and its per-step failure markers (RLF cause,
reject / setup-fallback / no-complete), live in the artifact subtrees — each
links back to this ladder. In a pcap the returning UE appears as a fresh initial
UL RRC transfer whose RRC container is a re-establishment request. Most
re-establishments in mobility runs follow a failed handover → `handover.md`.
