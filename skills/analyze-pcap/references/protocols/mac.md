# MAC-NR

## Purpose

The `mac.pcap` captures every MAC-NR PDU emitted by the DU (UL and DL).
Useful for inspecting RACH outcomes (RAR), BSR/CR exchanges, scheduling
patterns per RNTI, and HARQ feedback at the MAC-PDU level.

Note: PHY-level events (PRACH detection, CQI, BLER) are **not** in the pcap.
For PRACH detection failures, fall back to logs.

## Key tshark filters

```bash
# All MAC-NR PDUs
tshark -r mac.pcap -Y 'mac-nr'

# RAR (RACH response)
tshark -r mac.pcap -Y 'mac-nr.rar'

# Specific RNTI
tshark -r mac.pcap -Y 'mac-nr.rnti == <RNTI>'

# Per-RNTI packet counts
tshark -r mac.pcap -T fields -e mac-nr.rnti | sort | uniq -c | sort -rn
```

## Identifier mapping

- `mac-nr.rnti` — the C-RNTI (or RA-RNTI, SI-RNTI, P-RNTI) of the PDU.
- `mac-nr.direction` — `0` = UL, `1` = DL.

## What you can and can't see

| Visible | Not visible |
|---|---|
| MAC PDU bytes (sub-PDUs, LCIDs, control elements) | PHY layer (PRACH detection, CQI, BLER) |
| RAR contents (RAPID, TC-RNTI, TA command, UL grant) | HARQ retransmissions at the PHY layer |
| BSR, PHR, C-RNTI MAC CE | Scheduling decisions (use logs) |
| Padding | Per-symbol timing |

## Common signatures

- **No RAR after PRACH**: pcap can't show PRACH itself, but absence of any
  `mac-nr.rar` near the expected attach time means the DU never built a RAR.
  Check logs for `PRACH` detection or `RA-RNTI` events.
- **Repeated MAC PDUs to the same RNTI with no UL response**: UE never
  completed Msg3; pair with logs for `msg3_nok`.
- **C-RNTI MAC CE (LCID 28) right after RAR**: contention resolution; if
  followed by silence, contention failed.

## Parsing script

```bash
# Per-RNTI PDU counts and direction split
tshark -r mac.pcap -T fields -e mac-nr.rnti -e mac-nr.direction | \
    awk -F'\t' '{print $1"\t"$2}' | sort | uniq -c | sort -rn

# Use the overview helper for top-level counts
python3 ${CLAUDE_SKILL_DIR}/references/scripts/pcap_overview.py <mac.pcap>
```

## Accumulated knowledge
