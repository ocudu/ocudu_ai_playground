# correlate — query slot

Type-specific slot for the **query** activity; the driving playbook pulls this in.
Use it when the answer requires lining up ≥2 sources.

Read `cross-correlation.md` first if not already loaded — the join-key model below
is only a summary of it.

## question → tool

| Question | Tool |
|---|---|
| "Did every PRACH/PUSCH the UE sent reach the gNB?" | `correlate_radio.py <run-dir> --kind pusch` (and `--kind prach`) |
| "Is the UE↔gNB↔pcap on the same clock?" | `align_clocks.py <run-dir>` |
| "Trace UE 0003 end to end" | `map_ue_ids.py` + `correlate_radio.py --rnti`, guided by `procedures/attach-end-to-end.md` |
| "Which UE owns C-RNTI 0x4607 across the logs and pcap?" | `ue_table.py <run-dir> --where rnti=0x4607` (log, F1AP, NGAP and E1AP ids), guided by `ue-identity-map.md` |
| "Follow one UE through its handovers" | `ue_table.py <run-dir> --where ue_trace=N` (or `--where amf_ngap=…`), `--traces` for one row per UE |
| "Did the handover complete on the target cell?" | `procedures/handover-end-to-end.md` |
| "Which side dropped the UE — UE, radio, or gNB?" | `procedures/radio-link-failure.md` |

Scripts live in `${CLAUDE_SKILL_DIR}/scripts/correlate/` and are run with
`python3 <full path>`.

## anchor on the right key

Matching-key priority (full model in `cross-correlation.md`):

- **radio events** → `(SFN.slot, RNTI)` at the PHY layer — exact, and immune to
  clock skew. Prefer this whenever both sides report slots.
- **UE identity** → the Amarisoft UEID / C-RNTI chain (`ue-identity-map.md`). The
  UEID is stable across a handover; the C-RNTI is not.
- **CP events / pcap** → wall-clock UTC (raw `frame.time_epoch`), only after
  `align_clocks.py` has established the offset.

## scoping

Scope by `--rnti` **early** in multi-UE runs. Cap output; spill large join tables
to the `correlate-` prefixed cache file and report its path.

When a correlation needs one side's parsing detail, load that per-artifact subtree
in addition (`../ocudu/query.md`, `../amari-ue/query.md`, `../pcap/query.md`) —
this type is permitted to reach into the siblings it joins.
