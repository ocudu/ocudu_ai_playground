# tshark recipes (cross-cutting)

Recipes that don't fit a single protocol. For per-protocol filters see
`references/protocols/<proto>.md`.

## Confirm dissector binding on a pcap

```bash
tshark -r <file.pcap> -V -c 1 | head -40
```

Look for the `wireshark-upper-pdu` block and the inner protocol tree.

## Protocol hierarchy stats

```bash
tshark -r <file.pcap> -q -z io,phs
```

## Extract a compact event list, tab-separated, capped at 200 rows

```bash
tshark -r <file.pcap> \
    -T fields -t ad -E separator=$'\t' \
    -e frame.number -e frame.time_epoch \
    -e <proto>.procedureCode \
    | head -n 200
```

## Time-window filter (epoch range)

```bash
tshark -r <file.pcap> -Y 'frame.time_epoch >= X && frame.time_epoch < Y'
```

## Accumulated knowledge
