# RLC-NR

## Purpose

The `rlc.pcap` captures RLC-NR PDUs (AM, UM, and TM where relevant). Useful
for diagnosing retransmission storms, polling-bit misuse, status-PDU
problems, and bearer-specific traffic imbalances.

## Key tshark filters

```bash
# All RLC-NR PDUs
tshark -r rlc.pcap -Y 'rlc-nr'

# AM status PDUs (control PDU type 0)
tshark -r rlc.pcap -Y 'rlc-nr.am.cpt == 0x00'

# Per-bearer packet counts
tshark -r rlc.pcap \
    -T fields -e rlc-nr.bearer-type -e rlc-nr.bearer-id \
    | sort | uniq -c | sort -rn

# Polling-bit-set AM data PDUs
tshark -r rlc.pcap -Y 'rlc-nr.am.p == 1'
```

## Identifier mapping

- `rlc-nr.direction` — UL / DL.
- `rlc-nr.ueid` — UE index (DU-local, not C-RNTI).
- `rlc-nr.bearer-type` — SRB / DRB / CCCH.
- `rlc-nr.bearer-id` — bearer index within the type.
- `rlc-nr.mode` — AM / UM / TM.

## AM data fields

- `rlc-nr.am.sn` — sequence number.
- `rlc-nr.am.p` — polling bit.
- `rlc-nr.am.si` — segmentation info.
- `rlc-nr.am.so` — segment offset.

## AM control PDUs (status)

- `rlc-nr.am.cpt == 0x00` — STATUS PDU.
- `rlc-nr.am.ack-sn` — ACK SN.
- `rlc-nr.am.nack-sn` — NACK SN(s) (may repeat).

## What you can see

| Visible | Not visible |
|---|---|
| PDU types per bearer | PDCP-level events (use logs) |
| Sequence numbers, polling, segmentation | SDU reassembly outcome on the receiver |
| Status PDUs and NACKed SNs | Retransmission scheduling decisions |

## Common signatures

- **Repeated NACKs for the same SN**: retransmission storm; check
  `rlc-nr.am.nack-sn` over time, pair with MAC for HARQ behaviour.
- **All-zero status range**: receiver is fine; sender's polling cadence is
  the variable.
- **Polling bit always set**: sender is asking for status every PDU — usually
  configuration error or constant low buffer occupancy.

## Parsing script

```bash
# Per-bearer summary
tshark -r rlc.pcap \
    -T fields -E separator=$'\t' \
    -e rlc-nr.ueid -e rlc-nr.bearer-type -e rlc-nr.bearer-id -e rlc-nr.mode \
    | sort | uniq -c | sort -rn

python3 ${CLAUDE_SKILL_DIR}/references/scripts/pcap_overview.py <rlc.pcap>
```
