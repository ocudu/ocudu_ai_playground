# 3GPP spec map

Which 3GPP TS governs each protocol and procedure, so an analysis can cite the
authoritative clause. This is a **pointer table only** — no spec text is copied
here. For the canonical wording, invoke the **`spec-explorer`** skill with the TS
number + clause below; it resolves them to line-numbered excerpts from the
Release-18 corpus. Do not answer a 3GPP-behaviour question from memory.

## Protocols → TS

| Protocol / interface | TS | Layer |
|---|---|---|
| NR RRC | 38.331 | radio control plane |
| NR PDCP | 38.323 | L2 |
| NR RLC | 38.322 | L2 |
| NR MAC | 38.321 | L2 (incl. random access §5.1) |
| NR PHY | 38.211 / 38.212 / 38.213 / 38.214 / 38.215 | L1 |
| F1AP (CU↔DU) | 38.473 | F1-C |
| E1AP (CU-CP↔CU-UP) | 38.463 | E1 |
| NGAP (gNB↔AMF) | 38.413 | NG-C |
| XnAP (gNB↔gNB) | 38.423 | Xn-C |
| NR overall / procedures | 38.300 | stage-2 |
| 5GS NAS (5GMM/5GSM) | 24.501 | NAS |
| 5GS procedures (stage 2) | 23.502 | system |

## Procedures → clause

| Procedure | Primary clause(s) | See also |
|---|---|---|
| Random access | 38.321 §5.1 | 38.213 §8 (PDCCH order, RAR timing) |
| RRC connection setup | 38.331 §5.3.3 | — |
| Registration (NAS) | 24.501 §5.5.1; 23.502 §4.2.2.2 | — |
| Initial Context Setup | 38.413 §8.3 (NGAP) | drives F1AP UE Context + E1AP Bearer Context |
| UE Context Setup (F1) | 38.473 §8.3.1 | empty DU-to-CU container = "can't serve", §8.4.1.2 |
| Bearer Context Setup (E1) | 38.463 §8.3.1 | — |
| PDU Session Resource Setup | 38.413 §8.2 | 23.502 §4.3.2 |
| Handover (intra-NR) | 38.300 §9.2.3 | F1AP §8.4 / NGAP §8.4 / XnAP §8.4 |
| RRC re-establishment | 38.331 §5.3.7 | — |
| UE Context Release | 38.413 §8.3.3 (NGAP) | F1AP §8.3.3 |

## Handoff to spec-explorer

Give `spec-explorer` the TS number and the topic/clause, e.g. *"TS 38.473 UE
Context Setup Request DUtoCURRCContainer"* or *"TS 38.331 §5.3.7
re-establishment"*. Use it to confirm expected behaviour before attributing a log
anomaly to a spec violation.
