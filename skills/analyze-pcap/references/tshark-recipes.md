# tshark recipes

Vetted one-liners. Each recipe lists the question it answers, the command, and
where to look for fields if you need to extend it.

## General

### Confirm dissector binding on a pcap

```bash
tshark -r <file.pcap> -V -c 1 | head -40
```

Look for the `wireshark-upper-pdu` block and the inner protocol tree.

### Protocol hierarchy stats

```bash
tshark -r <file.pcap> -q -z io,phs
```

### Extract a compact event list, tab-separated, capped at 200 rows

```bash
tshark -r <file.pcap> \
    -T fields -t ad -E separator=$'\t' \
    -e frame.number -e frame.time_epoch \
    -e <proto>.procedureCode \
    | head -n 200
```

## NGAP

### List NGAP procedures with timestamps and UE IDs

```bash
tshark -r ngap.pcap \
    -T fields -E separator=$'\t' \
    -e frame.number -e frame.time_epoch \
    -e ngap.procedureCode \
    -e ngap.RAN_UE_NGAP_ID -e ngap.AMF_UE_NGAP_ID
```

### Only failures and rejects

```bash
tshark -r ngap.pcap \
    -Y 'ngap.unsuccessfulOutcome_element || ngap.cause'
```

### Initial UE attachment lifecycle for one UE

```bash
tshark -r ngap.pcap \
    -Y 'ngap.RAN_UE_NGAP_ID == <N>' \
    -T fields -e frame.number -e frame.time_epoch -e ngap.procedureCode
```

## F1AP

### List F1AP procedures and both UE IDs

```bash
tshark -r f1ap.pcap \
    -T fields -E separator=$'\t' \
    -e frame.number -e frame.time_epoch \
    -e f1ap.procedureCode \
    -e f1ap.GNB_DU_UE_F1AP_ID -e f1ap.GNB_CU_UE_F1AP_ID
```

### UEContextSetup outcomes

```bash
tshark -r f1ap.pcap \
    -Y 'f1ap.procedureCode == 5'
```

## E1AP

### Bearer context lifecycle

```bash
tshark -r e1ap.pcap \
    -T fields -E separator=$'\t' \
    -e frame.number -e frame.time_epoch \
    -e e1ap.procedureCode \
    -e e1ap.gNB_CU_CP_UE_E1AP_ID -e e1ap.gNB_CU_UP_UE_E1AP_ID
```

## MAC-NR

### All RAR PDUs (RACH responses)

```bash
tshark -r mac.pcap -Y 'mac-nr.rar'
```

### Per-RNTI packet counts

```bash
tshark -r mac.pcap -T fields -e mac-nr.rnti | sort | uniq -c | sort -rn
```

## RLC-NR

### Status PDUs (AM)

```bash
tshark -r rlc.pcap -Y 'rlc-nr.am.cpt == 0x00'
```

### Per-bearer packet counts

```bash
tshark -r rlc.pcap \
    -T fields -e rlc-nr.bearer-type -e rlc-nr.bearer-id \
    | sort | uniq -c | sort -rn
```

## Accumulated knowledge

*Append new vetted recipes here. Each entry: date — question answered —
command — note on when to use vs the helper scripts in `references/scripts/`.*
