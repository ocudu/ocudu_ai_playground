# Random Access (RA)

Pcap observation surface. The artifact-agnostic message ladder is
`../../common/procedures/random-access.md`; this file is the pcap view. For
diagnosing a *failed* RA, see `../troubleshooting/random-access.md`.

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

## Diagnosing failures

For failure markers (which step is missing → likely cause) and the tshark
checklist, see `../troubleshooting/random-access.md`.

## Cross-references

- `protocols/mac.md` — MAC fields used here.
- `protocols/f1ap.md` — F1AP procedures.
- `cross-pcap-correlation.md` — joining MAC and F1AP by RNTI.
