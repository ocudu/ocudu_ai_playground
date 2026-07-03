# Troubleshooting: attached but no user-plane data

The UE attached at the RRC level (`rrcSetupComplete`, Initial Context Setup done)
but **no data flows** — no `[GTPU]` SDUs, DRB never usable. The break is in
PDU-session / DRB setup (E1AP bearer + F1AP DRB plumbing).

For the **expected message sequence** (13 steps, E1AP↔F1AP↔GTPU), see
`../reference/pdu-session-setup.md`.

## Failure markers

| Where it fails | Marker | Likely cause |
|---|---|---|
| Step 5 missing | `BearerContextSetupRequest` not acknowledged | CU-UP not started or rejected the bearer (check `[CU-UP   ]` lines) |
| Step 5 ack with failure cause | `BearerContextSetupResponse` body shows failed bearers | QoS / DRB ID conflict — check PCAP for cause IE |
| Step 9 missing | DRB modification stalls | F1-U tunnel attach failed on DU |
| Step 13 missing despite reconfigComplete | `Tunnel added` not seen | GTPU layer at warning, or tunnel creation actually failed |
| Step 12 received but no UL data | `[GTPU] [I] UL teid=...: TX PDU` lines absent | UE not generating traffic, or NAS PDU session not activated on UE side |

## Investigation checklist

1. Did the bearer context come up?
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu/ocudu_log_search.py gnb.log --pattern "BearerContext(Setup|Modification)(Request|Response)" --max-lines 40
   ```
2. Did the F1-U tunnel attach?
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu/ocudu_log_search.py gnb.log --pattern "Attaching dl_teid|F1-U tunnel" --max-lines 20
   ```
3. Is the user-plane flowing?
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu/ocudu_log_search.py gnb.log --layer GTPU --max-lines 30
   ```
4. Did the reconfiguration land?
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu/ocudu_log_search.py gnb.log --pattern "rrcReconfiguration(Complete)?" --max-lines 30
   ```
5. If E1AP layer is at warning, enable `e1ap_level: info` in `ocudu_gnb.yml`
   for the next run, or analyse the `e1ap.pcap` via the `pcap` type.

## Cross-references

- `../reference/pdu-session-setup.md` — the expected DRB-setup sequence.
- `../reference/ue-attach.md` — bearer setup overlaps with the attach procedure.
- `ue-attach-failure.md` — if the attach itself did not complete.
- `pcap` type: `e1ap.pcap`, `f1ap.pcap` carry the full IE bodies.
</content>
