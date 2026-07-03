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
