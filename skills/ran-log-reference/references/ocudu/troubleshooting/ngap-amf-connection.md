# Troubleshooting: NGAP / AMF connection

The gNB's CU-CP failed to connect to the AMF or exchange NG Setup, or the NG
association dropped. Nothing useful happens in a run before this succeeds, so
this is the first thing to rule out when a run does nothing.

For the **expected SCTP + NG Setup sequence**, see `../reference/ngap-setup.md`.

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
   python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu/ocudu_log_search.py gnb.log --layer SCTP-GW --max-lines 20
   ```
2. Confirm NGAP layer is enabled and what it logged:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu/ocudu_log_search.py gnb.log --layer NGAP --max-lines 20
   ```
3. Cross-check the AMF endpoint in `ocudu_gnb.yml`:
   ```bash
   grep -A 6 "^cu_cp:" ocudu_gnb.yml | grep -E "addrs|port|bind_addrs"
   ```
4. On NGSetupFailure, inspect the cause IE in the NGAP PCAP if available
   (handoff to the `pcap` type with `ngap.pcap`).
5. If the AMF side is suspect, suggest checking the corresponding
   `amarisoft-5gc-*` sibling component if present.

## Cross-references

- `../reference/ngap-setup.md` — the expected SCTP + NG Setup sequence.
- `../reference/config-format.md` — § Field reference (`cu_cp.amf.*` rows).
- `pcap` type: `ngap.pcap` carries the NGSetup / cause IEs.
</content>
