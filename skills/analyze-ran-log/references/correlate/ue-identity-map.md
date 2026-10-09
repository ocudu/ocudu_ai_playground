# UE identity map (cross-artifact)

A single UE wears different identifiers in each artifact. To follow one UE across
the UE log, the gNB log, and the pcaps, anchor on the **most stable** ID and
follow the chain. (The identifier *model* — each ID's assigning node, scope, and
stability across HO/reestablishment — lives in `../common/identifiers.md`;
per-artifact field names live in each type subtree; this file is only the
cross-artifact joining.)

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

## Joining two OCUDU components (split deployment)

With CU-CP, CU-UP and DU as separate processes, each writes its own log and the
join is the **F1AP UE id pair** printed on both sides:

```bash
# Same UE, two logs: du_ue=N appears in [CU-CP-F1] on the CU and [DU-F1] on the DU
LC_ALL=C grep -a 'du_ue=' cu_cp.log | head -n 40
LC_ALL=C grep -a 'du_ue=' du.log    | head -n 40
```

`du=N tid=N du_ue=N` on a `Tx PDU`/`Rx PDU` line gives three keys at once:
`du_ue` joins the UE context across the two logs, `du` identifies which DU, and
**`tid` (transaction id) pairs a request with its response** — the same role it
plays for E1AP and NGAP. Use `tid` whenever you need to prove a specific response
belongs to a specific request rather than inferring it from ordering.

The CU-CP↔CU-UP join is the E1AP pair instead (`cu_cp_ue` / `cu_up_ue`); see the
identifier chain above.

- **RNTIs are recycled.** In a churn run the same RNTI is handed out many times,
  so confirm the RA-Complete you matched is the right one: grep the RNTI, and if
  it appears more than once, disambiguate by the gNB-side event (pick the
  occurrence whose outcome matches) or by time. The VIAVI `UE Id`, by contrast,
  is stable for the whole run — anchor on it.
- **The VIAVI clock is tester-local and may be offset from the gNB** — prefer the
  RNTI join over time (see cross-correlation.md § Clocks).
- **Failure-side join.** A VIAVI `NR CONNECTION FAILED IND:UE Id:<N>` (body
  `RRC: ... T300/T319 expired`) is the UE-side view of a failed RRC setup; join it
  to the gNB C-RNTI via that UE's preceding `Random Access Complete` TC-RNTI to
  read the network-side cause in `gnb.log`.

## One table per run (gNB log + F1AP, NGAP and E1AP pcaps)

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/ue_table.py <run-dir>                       # all UE contexts
python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/ue_table.py <run-dir> --traces              # one row per UE
python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/ue_table.py <run-dir> --where rnti=0x4607    # one RNTI
python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/ue_table.py <run-dir> --where amf_ngap=109 --traces
python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/ue_table.py <run-dir> --where du_ue=3 --after 12:24:30 --before 12:24:40
```

One row per UE context (one cell of a UE) with its lifetime, `rnti`, DU UE index `du_ue`, CU-CP UE index `cu_ue` (when
the CU logs at info), `du_f1ap`, `cu_f1ap`, and the `ue_trace` it belongs to with the NGAP (`ran_ngap`, `amf_ngap`) and
E1AP (`cu_cp_e1ap`, `cu_up_e1ap`) ids of that UE. A log context joins the F1AP context of the same C-RNTI with
overlapping lifetime; a handover target, created in the log before its RNTI, takes it from its first `UE
Configuration` line. A trace chains the contexts of a UE by the target C-RNTI of its handovers and the old C-RNTI of
its reestablishments, and joins its NGAP context by NAS PDU (or by the C-RNTI of the NGAP handover, on a target gNB)
and its E1AP context by UPF TEID. `--traces` prints one row per trace, with long id lists shortened to
`first,…,last (n)`. The DU and CU-CP UE indexes are different ids, both reused soon after a release, so filter them
with a time window or prefer the RNTI and protocol ids. Random accesses of no UE (PRACH only) are counted and hidden
unless `--with-ra`.

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
