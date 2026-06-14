# Random Access (RA)

The 4-step RA procedure (Msg1 → Msg2 → Msg3 → Msg4) is mostly **not visible**
in OCUDU pcaps: Msg1 (PRACH) is a PHY event, not a MAC PDU. What is visible:

- **Msg2 (RAR)** in `mac.pcap` as `mac-nr.rar`.
- **Msg3** in `mac.pcap` (UL MAC PDU, often containing a C-RNTI or CCCH
  payload) and in `f1ap.pcap` as `InitialULRRCMessageTransfer` once the RRC
  Setup Request reaches the CU.
- **Msg4** in `f1ap.pcap` (`DLRRCMessageTransfer` carrying RRC Setup) and in
  `mac.pcap` (the DL MAC PDU carrying the contention-resolution C-RNTI MAC CE).

For PRACH detection failures, the pcap is empty — fall back to the gNB log.

## Trigger event

A new UE attaching to the cell. Look in `f1ap.pcap` for the first
`InitialULRRCMessageTransfer` with no preceding F1AP context for that
`gNB-DU-UE-F1AP-ID`.

## Expected sequence across pcaps

```
mac.pcap     RAR with TC-RNTI = X                                            (T0)
mac.pcap     UL MAC PDU on RNTI = X (Msg3, often CCCH SDU = RRCSetupRequest) (T0 + a few ms)
f1ap.pcap    InitialULRRCMessageTransfer  (DU-UE-F1AP-ID = N, C-RNTI = X)    (T0 + a few ms)
f1ap.pcap    DLRRCMessageTransfer         (RRC Setup)                        (T0 + tens of ms)
mac.pcap     DL MAC PDU on RNTI = X (Msg4)                                   (T0 + tens of ms)
```

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

- `../protocols/mac.md` — MAC fields used here.
- `../protocols/f1ap.md` — F1AP procedures.
- `../cross-pcap-correlation.md` — joining MAC and F1AP by RNTI.
