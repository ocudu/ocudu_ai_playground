# VIAVI — investigate slot

Type-specific slot for the **investigate** activity. The driving playbook owns
the loop, the Found/Clues/Next block, and the Diagnosis template; this file only
supplies what is specific to this artifact.

## symptom — how to identify things here

- Which `UE Id` (decimal, e.g. `113`).
- Expected vs observed behaviour, and an approximate time window.

Run `overview.md`'s summary script if it hasn't run; treat its **Anomalies** as
primary leads.

## symptom → playbook

Ordered **most-specific first** — take the first row that matches.

| Symptom | Playbook |
|---|---|
| Random-access errors (`Max_Preambles_Exceeded`) | `troubleshooting/random-access.md` |
| Reestablishments / handover churn | `troubleshooting/random-access.md` — covers the RA-triggered case only; if RA is clean, escalate to `correlate` |
| UE never connected / `CONNECTION FAILED IND` | `troubleshooting/ue-attach.md` |
| UE connected but never `REGISTRATION IND` | `troubleshooting/ue-attach.md` |
| Low throughput / high BLER | `troubleshooting/throughput.md` |

Load the matching playbook and follow its failure markers / investigation
checklist. Each cites its `reference/<proc>.md` expected-sequence sibling for the
normal message ladder to compare against.

## checks specific to this type

- The VIAVI log is the **tester's** view. A failure here usually needs the OCUDU
  gNB log or a pcap to confirm the network-side cause — always name what to
  compare against.
- Tester command responses carry a status code: a non-`0x00` response means the
  *tester* rejected the command, which is a test-harness problem, not a RAN
  failure. Rule that out before investigating the network.
