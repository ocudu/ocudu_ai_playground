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

Ordered **most-specific first** — take the first row that matches, preferring one
whose marker you can actually point at (see the playbook's Phase B).

| Symptom | Playbook |
|---|---|
| Process crashed / abnormal exit | `troubleshooting/abnormal-exit.md` |
| NGAP / AMF connection lost or never established | `troubleshooting/ngap-amf-connection.md` |
| PHY-only failures (PRACH undecoded, persistent `crc=KO`, ZMQ rx waiting) | `troubleshooting/phy-issues.md` |
| UE stuck in fallback: `ra-ContentionResolutionTimer` expiry, RRC Setup/Reest timeout, or Msg4/ConRes never scheduled | `troubleshooting/ue-fallback-scheduling-issues.md` |
| RRC reestablishment seen (`rrcReestablishmentRequest`) | `troubleshooting/reestablishment.md` |
| Handover triggered but failed (no `rrcReconfigurationComplete` on target, or RLF after `reconfigurationWithSync`) | `troubleshooting/handover-failure.md` |
| UE released unexpectedly (and none of the above) | `troubleshooting/ue-release-issues.md` |
| UE never attached (no `UE created`, or no `Initial Context Setup Routine finished`) | `troubleshooting/ue-attach-failure.md` |
| UE attached but no data / DRB never set up | `troubleshooting/no-user-plane.md` |
| High DL/UL KOs / BLER (localize attach vs steady-state vs release first) | `troubleshooting/harq-ko-bler.md` |
| Throughput regression / late HARQs / failed PDCCH, BLER normal | `troubleshooting/throughput-degradation.md` |

Overlaps to be deliberate about:

- "UE never attached" is an *outcome*; a fallback-scheduling or PHY marker is a
  *cause*. If you can see the cause, start there — `ue-attach-failure.md` is the
  entry point when you can't.
- High BLER causes throughput regression. Take `harq-ko-bler.md` first and only
  fall to `throughput-degradation.md` when BLER is normal.
- A post-HO RLF matches handover, reestablishment and release. `handover-failure.md`
  owns it when `reconfigurationWithSync` preceded the drop.

Each playbook pairs failure markers with an investigation checklist and cites the
expected message sequence in its `reference/` sibling. Load the matching one and
work its checklist.

## checks specific to this type

- Scope every search by `--ue` / `--rnti` / `--pci` before widening a time window.
- A CU-side symptom with no DU-side counterpart (or vice-versa) in a split
  deployment means the next check belongs in the *other* component's log, not
  deeper in this one.
- Config-driven behaviour: compare `ocudu_gnb.yml` against the
  `[CONFIG  ] [D] gNB input configuration` echo before blaming the code — the
  effective value after merges is what ran (see `query.md`).
