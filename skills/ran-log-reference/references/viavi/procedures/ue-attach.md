# Procedure: UE attach (VIAVI)

How a simulated UE comes up in the VIAVI log: random access → RRC connection →
5GMM registration → PDU session. All events are `I: CMPI` lines keyed by
`UE Id:<N>` (decimal). See `log-format.md` § CMPI events for the exact line shapes.

## Expected sequence (one UE)

```
L2 Random Access Initiated :UE Id:N (Connection Establish: Cell Id C, Dl Freq F, SSB Id S)
L2 Random Access Complete  :UE Id:N (TC-RNTI: 0xXXXX, TimingAdv: T, PreambleTxCount: P)
MTE 0 NR CONNECTION IND:UE Id:N
MTE 0 NR REGISTRATION IND:UE Id:N
    Selected PLMN: 00101F
    Pdu Session Id: 1
    Data Network Name: <apn>
MTE 0 NR PDU SESSION MODIFICATION IND:UE Id:N        ← if the session is modified
```

A clean teardown later shows `NR DEREGISTRATION IND` then `NR DISCONNECTION IND`
for the same UE. In a churn test a UE may cycle connect/disconnect many times.

Trace one UE end to end:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/viavi/viavi_log_search.py <log> --ue N
```

## Failure markers

| Marker | Meaning |
|---|---|
| `L2 Random Access Error :UE Id:N (Result: …)` | PRACH never completed → see `procedures/random-access.md` |
| `MTE 0 NR CONNECTION FAILED IND:UE Id:N` | RRC connection attempt failed (no `CONNECTION IND` follows) |
| `CONNECTION IND` but no `REGISTRATION IND` | RRC up but 5GMM registration never completed — a core/NAS-side problem |
| `REGISTRATION IND` absent for a UE that has RA Complete | registration stalled; check the OCUDU gNB log / NGAP pcap |
| `NR PLMN LOSS IND` | UE lost the PLMN mid-session |

## Investigation checklist

1. Did RA complete? `--ue N --event "Random Access"` — if only `Initiated`/`Error`,
   the problem is at random access (next file).
2. Did the connection come up? `--ue N --event "NR CONNECTION"` — `CONNECTION
   FAILED IND` vs `CONNECTION IND`.
3. Did registration complete? `--ue N --event "NR REGISTRATION IND"`.
4. If RA + connection succeeded but registration didn't, the VIAVI side did its
   job — cross-check the **OCUDU gNB log** (RRC setup, NGAP Initial UE Message)
   and the **NGAP pcap** for the network-side cause.
