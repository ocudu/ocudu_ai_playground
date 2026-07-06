# Procedure: UE attach (VIAVI)

How a simulated UE comes up in the VIAVI log: random access → RRC connection →
5GMM registration → PDU session. All events are `I: CMPI` lines keyed by
`UE Id:<N>` (decimal). See `log-format.md` § CMPI events for the exact line shapes.

For diagnosing a *failed* attach, see `../troubleshooting/ue-attach.md`.

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

## Diagnosing failures

For failure markers and the investigation checklist, see
`../troubleshooting/ue-attach.md`.
