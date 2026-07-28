# pcap — investigate slot

Type-specific part of `references/mode-investigate.md` (which drives the loop, the
Found/Clues/Next block, and the Diagnosis template).

## symptom — how to identify things here

- Which pcap(s), and which run directory.
- Which UE, and by which identifier (C-RNTI, AMF-UE-NGAP-ID, GNB-CU-UE-F1AP-ID, …
  — see `reference/protocols/general.md`).
- Which event(s) appear missing or erroneous.
- Approximate timestamp window (epoch).

Run `overview.md`'s `pcap_overview.py` if it hasn't run for this input, to
establish the activity baseline. Treat the anomalies it flags as primary leads:
Failures, Rejects, unbalanced setup/release counts.

## symptom → playbook

| Symptom | Playbook |
|---|---|
| PRACH not detected, UE stuck before RRC Setup, Msg3 failures | `troubleshooting/random-access.md` |
| `InitialUEMessage` without `InitialContextSetupResponse`, AMF rejections | `troubleshooting/registration.md` |
| PDU Session Resource Setup Failure, zero throughput with UE attached | `troubleshooting/pdu-session-setup.md` |
| HandoverPreparation / HandoverCommand / UEContextSetup on target, CFRA / CBRA on target cell, re-establishment after HO | `troubleshooting/handover.md` |
| Unexpected `UEContextReleaseCommand`, cause IE pointing at RLF or AMF-initiated release | `troubleshooting/ue-context-release.md` |

Each playbook pairs failure markers with a tshark checklist and cites the expected
across-pcaps sequence in its `reference/` sibling. Load the matching one and work
it.

## checks specific to this type

- The capture shows what crossed the interface — an absent message means *either*
  it was never sent *or* the capture filter missed it. Confirm the pcap actually
  covers the window before concluding absence
  (`reference/cross-pcap-correlation.md`).
- Sibling pcaps are the cheapest next check: the same procedure appears in
  `ngap`/`f1ap`/`e1ap` at slightly different epochs. Non-overlapping time ranges
  across siblings are themselves an anomaly.
- Prefer procedure **codes** over dissector display names when grepping — names
  vary by Wireshark version.
