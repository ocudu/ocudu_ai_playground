# OCUDU pcap format — Wireshark Upper PDU (DLT 252)

## What these pcaps actually contain

OCUDU writes captures in the **Wireshark Upper PDU** export format
(link-layer type 252, `WTAP_ENCAP_WIRESHARK_UPPER_PDU`). Each record begins
with a small `wireshark-upper-pdu` header.

- **Control-plane pcaps** (`ngap`, `f1ap`, `e1ap`) carry a `dissector_name`
  string (`ngap`/`f1ap`/`e1ap`) and **auto-dispatch** to the right dissector —
  `frame.protocols` ends in `...:ngap` etc.
- **`mac.pcap` / `rlc.pcap` are different**: the Upper-PDU `Protocol Name` is
  `udp`, and the NR PDU is carried inside a UDP frame (ports 0xbeef/0xdead).
  `frame.protocols` is `exported_pdu:udp:data` — tshark does **not** reach the
  MAC-NR/RLC-NR dissector by default, so every `mac-nr.*`/`rlc-nr.*` field and
  `-Y mac-nr`/`-Y rlc-nr` filter returns nothing **unless** the UDP heuristic
  dissectors are enabled (see below).

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

## Dissection

Control-plane pcaps auto-dispatch; standard filters work directly:

```bash
tshark -r ngap.pcap -Y 'ngap.procedureCode == 14'   # InitialContextSetup
tshark -r f1ap.pcap -Y 'f1ap.procedureCode == 5'    # UEContextSetup
tshark -r e1ap.pcap -Y 'e1ap.procedureCode == 8'    # bearerContextSetup
```

**MAC/RLC require the UDP heuristic dissectors** (they ship disabled). Add
`--enable-heuristic mac_nr_udp` / `--enable-heuristic rlc_nr_udp` to every
read; without them the filters silently return zero:

```bash
tshark -r mac.pcap --enable-heuristic mac_nr_udp -Y 'mac-nr'          # MAC-NR PDUs
tshark -r mac.pcap --enable-heuristic mac_nr_udp -e mac-nr.rnti -e mac-nr.direction -T fields
tshark -r rlc.pcap --enable-heuristic rlc_nr_udp -Y 'rlc-nr'          # RLC-NR PDUs
```

The helper scripts inject both flags automatically for any `-r` read
(`utils.run_tshark`), so script-driven analysis already works; only **hand-run**
tshark on `mac.pcap`/`rlc.pcap` needs the flags added explicitly.

For the full per-protocol code tables, see the protocol files under
`references/protocols/`.

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
