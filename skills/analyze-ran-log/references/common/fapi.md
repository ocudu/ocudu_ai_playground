# FAPI — MAC ↔ PHY interface

FAPI (SCF 222, "5G FAPI: PHY API") is the message interface between the L2/MAC
scheduler and the L1/PHY in a split-option-6 deployment. It is a reference for
*interpreting* PHY/MAC timing and per-slot outcomes — a scheduler decision (a
grant, a CSI request) crosses to the PHY as a FAPI message, and the PHY reports
what it received back as a FAPI indication. Where these appear in a given artifact
is per-artifact detail; the message *meanings* are here.

## P5 — cell configuration / control (infrequent)

| Message | Direction | Meaning |
|---|---|---|
| `PARAM.request` / `.response` | MAC↔PHY | query PHY capabilities |
| `CONFIG.request` / `.response` | MAC→PHY | configure the cell (numerology, carrier, PRACH, …) |
| `START.request` | MAC→PHY | begin slot processing |
| `STOP.request` / `.indication` | MAC↔PHY | halt slot processing |
| `ERROR.indication` | PHY→MAC | config/slot error (out-of-order, invalid SFN.slot, …) |

## P7 — per-slot data path (one set per slot)

Downlink / requests (MAC→PHY):

| Message | Meaning |
|---|---|
| `SLOT.indication` | PHY→MAC slot-boundary tick; anchors all per-slot timing |
| `DL_TTI.request` | DL channels scheduled this slot: SSB, PDCCH (DCI), PDSCH, CSI-RS |
| `UL_DCI.request` | PDCCH carrying UL grants (DCI) for this slot |
| `TX_DATA.request` | MAC PDU payload for the scheduled PDSCH |
| `UL_TTI.request` | UL transmissions the PHY should expect: PUSCH, PUCCH, PRACH, SRS |

Uplink indications (PHY→MAC):

| Message | Meaning |
|---|---|
| `RX_DATA.indication` | decoded PUSCH MAC PDU |
| `CRC.indication` | PUSCH decode result (CRC pass/fail) — feeds HARQ |
| `UCI.indication` | PUCCH/PUSCH-carried UCI: HARQ-ACK, SR, CSI |
| `RACH.indication` | detected PRACH preambles (RA-RNTI, preamble, timing advance) |
| `SRS.indication` | SRS channel measurements |

## Reading FAPI against a run

- A per-slot cadence issue (missed `SLOT.indication`, late `DL_TTI.request`) points
  at the L1↔L2 boundary rather than the scheduler logic.
- `UCI.indication` carries the UCI outcome vocabulary — HARQ-ACK/NACK/DTX, SR
  positive/negative, CSI valid/invalid; the per-artifact subtree names how each
  outcome is printed.
- `RACH.indication` is the PHY's view of random access; it is the FAPI counterpart
  of the scheduler's PRACH-detected event — see `procedures/random-access.md`.
