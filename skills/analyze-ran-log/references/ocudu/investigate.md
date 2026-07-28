# OCUDU — investigate slot

Type-specific slot for the **investigate** activity. The driving playbook owns
the loop, the Found/Clues/Next block, and the Diagnosis template; this file only
supplies what is specific to this artifact.

## symptom — how to identify things here

- Which component: `ocudu-gnb-*` vs `ocudu-cu-*` vs `ocudu-du-*`.
- Which UE, and by which identifier: `ue=N` on the **CU** side, `c-rnti=0xNNNN` on
  the **DU** side, `amf_ue_ngap_id` on the **AMF/NGAP** side.
- Approximate timestamp window — from the procedure timeline the summary script
  produces, or from `[METRICS]` rows.

Run `overview.md`'s summary script if it hasn't run for this input. Treat the
anomalies it flags as primary leads: warnings/errors, late HARQs, NGAP setup
failure, RRC reestablishment, msg3 NACKs, abnormal shutdown, dropped traffic.

## symptom → playbook

| Symptom | Playbook |
|---|---|
| UE never attached (no `UE created`, or no `Initial Context Setup Routine finished`) | `troubleshooting/ue-attach-failure.md` |
| UE stuck in fallback: `ra-ContentionResolutionTimer` expiry, RRC Setup/Reest timeout, or Msg4/ConRes never scheduled | `troubleshooting/ue-fallback-scheduling-issues.md` |
| UE attached but no data / DRB never set up | `troubleshooting/no-user-plane.md` |
| Handover triggered but failed (no `rrcReconfigurationComplete` on target, or RLF after `reconfigurationWithSync`) | `troubleshooting/handover-failure.md` |
| RRC reestablishment seen (`rrcReestablishmentRequest`) | `troubleshooting/reestablishment.md` |
| UE released unexpectedly | `troubleshooting/ue-release-issues.md` |
| NGAP / AMF connection lost or never established | `troubleshooting/ngap-amf-connection.md` |
| PHY-only failures (PRACH undecoded, persistent `crc=KO`, ZMQ rx waiting) | `troubleshooting/phy-issues.md` |
| Throughput regression / late HARQs / failed PDCCH | `troubleshooting/throughput-degradation.md` |
| High DL/UL KOs / BLER (localize attach vs steady-state vs release first) | `troubleshooting/harq-ko-bler.md` |
| Process crashed / abnormal exit | `troubleshooting/abnormal-exit.md` |

Each playbook pairs failure markers with an investigation checklist and cites the
expected message sequence in its `reference/` sibling. Load the matching one and
work its checklist.

## checks specific to this type

- Scope every search by `--ue` / `--rnti` / `--pci` before widening a time window.
- A CU-side symptom with no DU-side counterpart (or vice-versa) in a split
  deployment means the next check belongs in the *other* component's log, not
  deeper in this one.
- Config-driven behaviour: compare `ocudu_gnb.yml` against the
  `[CONFIG  ] [D] Input configuration` echo before blaming the code — the
  effective value after merges is what ran (see `query.md`).
