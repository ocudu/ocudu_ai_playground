# Troubleshooting: Random Access (RA)

RA fails or stalls across the pcaps — no RAR, no Msg3, or the RRC Setup never
comes back. For the **expected across-pcaps sequence** this walks against, see
`../reference/random-access.md`. Recall the RA is mostly invisible in pcaps
(Msg1/PRACH is a PHY event) — for PRACH detection failures the pcap is empty,
fall back to the gNB log.

## Failure markers

| Symptom | Cause hypothesis |
|---|---|
| No RAR in `mac.pcap` | PRACH not detected — check logs. |
| RAR present, no Msg3 UL PDU on TC-RNTI | UE didn't transmit Msg3 (coverage, mis-tuned UE). |
| Msg3 PDU present, no `InitialULRRCMessageTransfer` | DU dropped Msg3 — RAPID mismatch, contention with another UE. |
| `InitialULRRCMessageTransfer` present, no RRC Setup back | CU side issue — check `f1ap.pcap` for outgoing DLRRCMessageTransfer; if absent, CU log. |
| RA succeeds for some UEs, fails for others on the same cell | Contention or RAPID collision; correlate with PRACH-occasion logs. |

## tshark filters

```bash
# All RAR PDUs in order (mac.pcap needs the MAC-NR UDP heuristic)
tshark -r mac.pcap --enable-heuristic mac_nr_udp -Y 'mac-nr.rar' \
    -T fields -e frame.number -e frame.time_epoch -e mac-nr.rnti

# First F1AP per UE (procedureCode 11 = InitialULRRCMessageTransfer)
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 11' \
    -T fields -e frame.number -e frame.time_epoch \
    -e f1ap.GNB_DU_UE_F1AP_ID -e f1ap.C_RNTI
```

## Cross-references

- `../reference/random-access.md` — the expected RA sequence this walks against.
- `../reference/protocols/mac.md` — MAC fields used here.
- `../reference/protocols/f1ap.md` — F1AP procedures.
- `../reference/cross-pcap-correlation.md` — joining MAC and F1AP by RNTI.
