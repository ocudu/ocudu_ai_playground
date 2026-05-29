# Procedure: NGAP / AMF connection

Connects the gNB's CU-CP to the AMF over SCTP and exchanges NG Setup so the gNB
can serve UEs. This is the first thing that has to succeed in a run; nothing
useful happens before it.

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

## Failure markers

| Marker | Likely cause |
|---|---|
| `[SCTP-GW ] [E] N2: SCTP connect to <ip>:<port> failed` | AMF unreachable, wrong IP/port, firewall, AMF down |
| `[NGAP    ] [I] Rx PDU: NGSetupFailure` | TAC / PLMN / slice (sst/sd) mismatch with AMF — check `cu_cp.amf.supported_tracking_areas` against AMF config |
| No `NGSetupResponse` and SCTP connected | AMF accepted SCTP but never sent NGSetupResponse — usually a slow / wedged AMF |
| `[CU-CP   ] [I] Trying to reconnect to AMF` | NG association dropped after a successful setup |
| Whole NGAP section missing despite `cu_cp.amf.addrs` set | `ngap_level: warning` silences the trace — check `ocudu_gnb.yml` |

## Investigation checklist

1. Confirm SCTP layer:
   ```bash
   python3 ocudu_log_search.py gnb.log --layer SCTP-GW --max-lines 20
   ```
2. Confirm NGAP layer is enabled and what it logged:
   ```bash
   python3 ocudu_log_search.py gnb.log --layer NGAP --max-lines 20
   ```
3. Cross-check the AMF endpoint in `ocudu_gnb.yml`:
   ```bash
   grep -A 6 "^cu_cp:" ocudu_gnb.yml | grep -E "addrs|port|bind_addrs"
   ```
4. On NGSetupFailure, inspect the cause IE in the NGAP PCAP if available
   (handoff to `analyze-pcap` with `ngap.pcap`).
5. If the AMF side is suspect, suggest checking the corresponding
   `amarisoft-5gc-*` sibling component if present.

## Cross-references

- Config: `references/config-format.md` § AMF block (`cu_cp.amf.*`).
- Companion artifact: `ngap.pcap` (analyze with `analyze-pcap`).
