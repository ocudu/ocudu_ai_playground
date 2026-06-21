# UE identity map (cross-artifact)

A single UE wears different identifiers in each artifact. To follow one UE across
the UE log, the gNB log, and the pcaps, anchor on the **most stable** ID and
follow the chain. (Per-layer detail on each ID lives in `ocudu`;
this file is only the cross-artifact joining.)

## The chain

```
Amarisoft UEID (ue.log)  ──RNTI──►  C-RNTI  ──►  CU ue= / ran_ue=  ──►  amf_ue=
   (most stable)            │         (per cell;       (gNB CU;          (AMF;
                            │          changes on HO)   NGAP)             5GC NAS UEID)
                            ▼
                      DU du_ue= / DU-local ue=     cu_cp_ue= / cu_up_ue= (E1AP; 2nd most stable)
                      (F1AP; pcap f1ap)            (pcap e1ap)
```

- **Amarisoft UEID** (`ue.log`, 4-hex e.g. `0035`) — fixed for the whole run;
  the anchor for correlating the UE log to a gNB UE context. Stable across HO,
  reestablishment, and brief releases.
- **VIAVI `UE Id`** (`*_Command_Log*.txt`, decimal `0`–`N`) — the VIAVI-tester
  analogue of the Amarisoft UEID: fixed for the whole run, the anchor for
  correlating the VIAVI log to a gNB UE context. The bridge to the gNB side is the
  **C-RNTI**, printed on the VIAVI `L2 Random Access Complete` line (see § Joining
  via the VIAVI log).
- **C-RNTI** — joins the UE PHY/MAC to the gNB PHY/MAC/SCHED/RRC; the PHY radio
  key together with SFN.slot. Changes on HO and reestablishment.
- **CU `ue=` / `ran_ue=`** — the gNB CU-internal index; `ran_ue` is the same value
  on NGAP. Visible in the `ngap.pcap`.
- **`amf_ue=`** — AMF-assigned (first DownlinkNASTransport). In these runs the 5GC
  NAS UEID maps to it (e.g. `mme.log [NAS] UL 0064 ...` ↔ gNB `amf_ue=100`,
  0x64 = 100). Joins the gNB to the 5GC.
- **`cu_cp_ue=`/`cu_up_ue=`** (E1AP, `e1ap.pcap`) — second-most-stable; survive
  intra-CU HO (bearer is modified, not recreated). A large gap between `ue=N` and
  `cu_cp_ue=K` means the UE has been through several HO cycles.

## Joining via logs

```bash
# Amarisoft UEID -> RNTI (UE log: RNTI is the field after the cell index CC)
grep " <UEID> " ue.log | grep -v '    -  ' | head -3

# RNTI -> CU ue=N (gNB log)
grep "ue=<N> c-rnti=0x<RNTI>: UE created" gnb.log

# CU ue=N -> DU-local ue / du_ue (gNB log)
grep -E "ue=.*du_ue=<N>|c-rnti=0x<RNTI>.*du_ue=<N>" gnb.log
```

## Joining via the VIAVI log

The VIAVI log keys on the decimal `UE Id`; the gNB keys on the C-RNTI. The bridge
is the **Random Access Complete** line, which prints both:

```bash
# VIAVI UE Id -> (T)C-RNTI: the RA-Complete line pairs them
LC_ALL=C grep -a 'Random Access Complete' "$L" | grep 'UE Id:<N>'
#   ... :UE Id:<N> (TC-RNTI: 0x<RNTI>, TimingAdv: …, PreambleTxCount: …)

# C-RNTI -> VIAVI UE Id (reverse): which simulated UE got this RNTI
LC_ALL=C grep -a 'TC-RNTI: 0x<RNTI>' "$L"
```

`TC-RNTI` is the temporary C-RNTI from the RAR; on contention resolution it
becomes the UE's C-RNTI, so it joins directly to the gNB's `c-rnti=0x<RNTI>`.

- **RNTIs are recycled.** In a churn run the same RNTI is handed out many times,
  so confirm the RA-Complete you matched is the right one: grep the RNTI, and if
  it appears more than once, disambiguate by the gNB-side event (pick the
  occurrence whose outcome matches) or by time. The VIAVI `UE Id`, by contrast,
  is stable for the whole run — anchor on it.
- **The VIAVI clock may not share the gNB's UTC epoch.** The tester's timestamps
  can sit on a different timezone/epoch than `gnb.log` (a several-hour offset, and
  the VIAVI window may not even span the same wall-clock as the gNB run). Prefer
  the RNTI join over time; if you must align by time, derive the offset from a
  uniquely-matched RNTI event first rather than assuming shared UTC.
- **Failure-side join.** A VIAVI `NR CONNECTION FAILED IND:UE Id:<N>` (body
  `RRC: ... T300/T319 expired`) is the UE-side view of a failed RRC setup; join it
  to the gNB C-RNTI via that UE's preceding `Random Access Complete` TC-RNTI to
  read the network-side cause in `gnb.log`.

## Joining via pcaps

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/map_ue_ids.py f1ap.pcap   # du_ue ↔ cu_ue ↔ c_rnti
python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/map_ue_ids.py ngap.pcap   # ran_ue ↔ amf_ue
python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/map_ue_ids.py e1ap.pcap   # cu_cp_ue ↔ cu_up_ue
```

Protocol is auto-detected from the filename. Each prints one line per
mapping update or release (`... [released]`). For inter-DU HO, run on both DU
pcaps: the source DU shows `UEContextRelease`, the target DU `UEContextSetup`.

## Stability across procedures (which IDs change)

| Identifier | Intra-CU HO | Reestablishment | Full release + re-attach |
|---|---|---|---|
| Amarisoft UEID | stable | stable | stable |
| VIAVI UE Id | stable | stable | stable |
| C-RNTI | **changes** | **changes** | resets |
| CU ue= / ran_ue | **changes** | stable (direct RLF) / changes (post-HO) | resets |
| amf_ue | stable | stable | resets |
| cu_cp_ue / cu_up_ue | **stable** | stable | resets |
| DU-local ue= (recycled) | **changes** | new | resets |

**Anchor on the Amarisoft UEID** (or the VIAVI `UE Id` for a VIAVI run) when
correlating the tester log to a specific gNB context; anchor on `cu_cp_ue` when
following a UE through handovers.
