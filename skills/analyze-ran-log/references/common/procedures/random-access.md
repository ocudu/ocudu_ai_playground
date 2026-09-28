# Procedure: Random access — abstract ladder

The 4-step contention-based RA (Msg1 → Msg2 → Msg3 → Msg4) that a UE uses to
enter connected mode, and the contention-free (CFRA) variant used on a handover
target. It is the first steps of an attach (`ue-attach.md` steps 1–4) and of a
reestablishment. Spec: TS 38.321 §5.1, TS 38.213 §8 (see `../spec-map.md`).

## Message ladder

| # | Message (abstract) | Between | Where seen |
|---:|---|---|---|
| 1 | Msg1 = PRACH preamble → RA-RNTI detected | UE → gNB PHY | gNB log (SCHED/PHY), UE log (PHY), VIAVI (`Random Access Initiated`) — **not** in pcap (PHY event) |
| 2 | Msg2 = RAR (TC-RNTI, TA, UL grant for Msg3) | gNB → UE | gNB log (SCHED), pcap `mac` (`mac-nr.rar`), VIAVI (`Random Access Complete` carries TC-RNTI) |
| 3 | Msg3 = first UL (CCCH: RRC Setup/Reest Request, or C-RNTI CE) | UE → gNB | gNB log (MAC), pcap `mac` (UL PDU) + `f1ap` (InitialULRRCMessageTransfer) |
| 4 | Msg4 = contention resolution (C-RNTI MAC CE) | gNB → UE | gNB log (MAC), pcap `mac` (DL PDU) + `f1ap` (DLRRCMessageTransfer, RRC Setup) |

CFRA (handover target): the gNB pre-assigns a dedicated preamble, so Msg3/Msg4
contention resolution is skipped and a HO can complete with **no visible PRACH
retry** — that absence is normal, not a failure.

## 2-step RA type (MsgA/MsgB)

Collapses Msg1+Msg3 into **MsgA** (PRACH preamble + a PUSCH payload, e.g. a CCCH
SDU carrying `rrcSetupRequest`) and Msg2+Msg4 into **MsgB**. Spec: TS 38.321
§5.1.3a/§5.1.4a (procedure), §6.1.5a/§6.2.2a/§6.2.3a (MsgB PDU format), TS 38.213
§8.2A (response window / PUCCH for MsgB HARQ feedback).

| # | Message (abstract) | Between | Where seen |
|---:|---|---|---|
| A | MsgA = PRACH preamble + PUSCH (CCCH SDU) | UE → gNB | gNB log (`[SCHED]` `MsgA`/`prach`, `[MAC]` UL subPDUs), UE log (PHY `PRACH:` + PUSCH) |
| B | MsgB = fallbackRAR (fall back to 4-step, like RAR) **or** successRAR (completes RA) | gNB → UE | gNB log (`[SCHED]` `MsgB: msgb-rnti=0xN ... tbs=N`), UE log (`[MAC] DL ... MSGB: uecri=...`) |

**MsgB has two spec-legal wire formats, selected by the `S` bit in the
successRAR subheader (§6.2.2a) — both are valid, neither is a bug by itself:**

- `S=0`, "successRAR only" (Fig 6.1.5a-5): the MsgB TB carries *only* the fixed
  12-byte successRAR (UE ConRes ID echo, TA, PUCCH/TPC/HARQ-timing fields,
  C-RNTI — §6.2.3a). It does **not** carry the RRC message. If the RA was
  triggered by an RRC procedure (e.g. `rrcSetupRequest`), the network must then
  schedule the RRC response (e.g. `RRCSetup`) as an **ordinary follow-up PDSCH
  under the newly-assigned C-RNTI** — an ordinary DL-SCH grant, not part of the
  RA procedure itself.
- `S=1`, "successRAR + MAC SDU(s)" (Fig 6.1.5a-4): the RRC message rides in the
  *same* transport block as the successRAR, as a MAC SDU on CCCH/DCCH/DTCH
  placed immediately after it.

Per §5.1.4a, the UE considers the **Random Access procedure itself** successfully
completed as soon as it decodes a matching successRAR (any `S` value) — there is
no RA-procedure-level timer covering delivery of a follow-up RRC message under
the `S=0` path; that delivery is governed by ordinary RRC timers (e.g. `T300` for
RRC setup), not by anything in 38.321/38.213. So: **if a UE ACKs MsgB/successRAR
cleanly but then never receives the follow-up C-RNTI-addressed PDSCH, do not
assume the network's choice of `S=0` was the defect** — check which format the
gNB actually used (its `tbs` — 12 bytes is the fixed successRAR-only size) before
concluding anything, and treat "UE never resumes PDCCH monitoring under the new
C-RNTI" as a live, equally-likely hypothesis on the **UE** side (see
`../../correlate/procedures/attach-end-to-end.md` § 2-step RA notes).

## Observation notes

- Msg1 is a **PHY event**, invisible in pcaps — for PRACH-detection failures fall
  back to the gNB log (or the UE-log PHY / VIAVI RA lines).
- `PreambleTxCount` (UE/VIAVI side) = preambles sent before success; 1 = first-shot,
  high = poor coverage / contention.
- The RA trigger (VIAVI `<trigger>`) tells you *why*: `Connection Establish`
  (initial), `Handover` (CFRA), `SR MAX Exceeded` / `SR NO Resource` (SR→RA
  fallback).

## Observation & diagnosis

How each step appears, and its per-step failure markers, live in the artifact
subtrees — each links back to this ladder. RA is a two-sided procedure: always
confirm the UE/VIAVI (tester) view against the gNB (network) view. In the abstract
flow RA is the entry to an attach (`ue-attach.md`) and a re-establishment
(`reestablishment.md`).
