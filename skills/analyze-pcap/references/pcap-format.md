# OCUDU pcap format — Wireshark Upper PDU (DLT 252)

## What these pcaps actually contain

OCUDU writes captures in the **Wireshark Upper PDU** export format
(link-layer type 252, `WTAP_ENCAP_WIRESHARK_UPPER_PDU`). Each record begins
with a small `wireshark-upper-pdu` header whose `dissector_name` field carries
a string that tells Wireshark which application-layer dissector to invoke.
Strings observed: `ngap`, `f1ap`, `e1ap`, `mac-nr-framed`, `rlc-nr`.

The captures **do not** contain L1/PHY frames, IP, Ethernet, or SCTP — only
the application-layer 3GPP PDUs as they leave the protocol layer. One pcap
file is produced per protocol; a typical OCUDU run yields five sibling files
in the same directory.

## File-naming convention

```
.../ocudu-gnb-<N>-<M>/<YYYY-MM-DD_HH-MM-SS>/
    mac.pcap        # MAC-NR PDUs
    rlc.pcap        # RLC-NR PDUs
    f1ap.pcap       # F1AP PDUs (CU–DU control)
    e1ap.pcap       # E1AP PDUs (CU-CP–CU-UP control)
    ngap.pcap       # NGAP PDUs (gNB–AMF)
```

Not every test produces all five. Single-UE attach tests sometimes write only
`rlc.pcap`; multi-UE and handover tests typically write all five.

## Timestamps

All pcaps share a wall-clock epoch reference (microsecond precision; libpcap
classic format). To align events across the 5 files, use `frame.time_epoch`
directly — see `cross-pcap-correlation.md`.

## Dissection — happy path

tshark 4.4.7 auto-dispatches via the `wireshark-upper-pdu` header on first
read. Standard display filters work out of the box:

```bash
tshark -r ngap.pcap -Y 'ngap.procedureCode == 14'   # InitialContextSetup
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 5'    # UEContextSetup
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 8'    # bearerContextSetup
tshark -r mac.pcap  -Y 'mac-nr'                     # any MAC-NR PDU
tshark -r rlc.pcap  -Y 'rlc-nr'                     # any RLC-NR PDU
```

For the full per-protocol code tables, see the protocol files under
`references/protocols/`.

## Dissection — fallback (rare)

If `tshark -r <file.pcap> -Y '<proto>'` returns zero packets despite the file
containing the protocol, the dissector name string in the Upper PDU header
may differ from the dissector identifier tshark expects. Symptoms:

- `tshark -r mac.pcap -Y 'mac-nr'` returns nothing but the file is non-empty.
- `tshark -V -c 1 -r <file.pcap>` shows the wrong protocol tree.

Workaround: force the dissector via `-d user_dlt`:

```bash
tshark -r mac.pcap -d user_dlt:252,mac-nr-framed -V -c 1
```

The dissector identifier to map to depends on the Upper-PDU header content.
Record any newly observed mapping here in this fallback section.

## Why this format matters for analysis

- **No PHY**. PRACH detection cannot be observed in `mac.pcap`; only the
  resulting `RACH-RAR` MAC PDU (if it was sent) is visible. To debug PRACH
  itself, fall back to logs.
- **No SCTP**. NGAP/F1AP/E1AP retransmissions and SCTP-level events are
  invisible. AMF "connection drop" events appear only in logs.
- **No IP**. GTP-U tunnel traffic does not show up; only the E1AP control
  messages that establish bearers do.
- **Per-PDU only**. Each pcap record is one fully-formed application PDU. No
  fragmentation, no segmentation reassembly required.

## Quick checks

```bash
capinfos -aeucz <file.pcap>            # counts, duration, time range
tshark -r <file.pcap> -V -c 1          # confirm dissector binding (first frame)
tshark -r <file.pcap> -q -z io,phs     # protocol hierarchy stats
file <file.pcap>                       # confirm magic header
```

## AppArmor on Ubuntu/Debian

`/usr/bin/tshark` ships with a Canonical AppArmor profile
(`/etc/apparmor.d/tshark`) that confines reads to `/tmp` and a handful of
system paths via `<abstractions/user-tmp>`. Pcaps under `~/srs/`, `/data/`,
etc. fail with `tshark: You don't have permission to read the file ...` even
though Unix permissions allow it. `cat` on the same file works — that's the
giveaway.

The helper scripts in `references/scripts/` handle this transparently:
`utils.stage_for_tshark()` hard-links (or copies on a different filesystem)
the source pcap into the per-session cache dir's `pcap-stage/` subfolder
(`${CLAUDE_CODE_TMPDIR:-/tmp}/claude-skills-${CLAUDE_CODE_SESSION_ID}/pcap-stage/<sha>-<basename>.pcap`)
and points tshark at that path. Staged files live under `/tmp` and so satisfy
the AppArmor confinement; the directory is reused for the lifetime of the
Claude session.

If running tshark by hand against a confined path, do the same — stage into
any directory under `/tmp` (the session cache dir is a fine choice):

```bash
STAGE="${CLAUDE_CODE_TMPDIR:-/tmp}/claude-skills-${CLAUDE_CODE_SESSION_ID}/pcap-stage"
mkdir -p "$STAGE"
ln -f <source.pcap> "$STAGE/x.pcap"
tshark -r "$STAGE/x.pcap" ...
```

A permanent fix is a local override file at `/etc/apparmor.d/local/tshark`
adding `file r /home/*/srs/**,` (requires `sudo systemctl reload apparmor`).
The script-side workaround is preferred because it needs no root.
