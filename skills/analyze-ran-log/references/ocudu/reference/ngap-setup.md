# Procedure: NGAP / AMF connection

gNB-log observation surface. The artifact-agnostic message ladder is
`../../common/procedures/ngap-setup.md`; this file maps it to the OCUDU `gnb.log`
lines. For a connection that failed or dropped, diagnose with
`../troubleshooting/ngap-amf-connection.md`.

Connects the gNB's CU-CP to the AMF over SCTP and exchanges NG Setup so the gNB
can serve UEs — the first thing that must succeed in a run.

## Expected sequence

1. `[SCTP-GW ] [I] N2: Bind to N address(es) was successful`
2. `[SCTP-GW ] [I] N2: Successfully connected to N address(es) using sctp_connectx()`
3. `[SCTP-GW ] [I] N2: SCTP connection to AMF established. Configured: [...], established: [...]`
4. `[CU-CP   ] [I] N2: Connection to AMF on <ip>:<port> was established`
5. `[NGAP    ] [I] Tx PDU: NGSetupRequest`
6. `[NGAP    ] [I] Rx PDU: NGSetupResponse`
7. `[CU-CP   ] [I] Connected to AMF. Supported PLMNs: <list>`

In `stdout.log` the milestone is `N2: Connection to AMF on <ip>:<port>
completed` followed by `==== gNB started ===`.

## Diagnosing failures

For failure markers (SCTP connect failure, NGSetupFailure cause, dropped
association) and the investigation checklist, see
`../troubleshooting/ngap-amf-connection.md`.

## Cross-references

- `config-format.md` — § Field reference (`cu_cp.amf.*` rows).
- Companion artifact: `ngap.pcap` (analyze with the `pcap` type).
