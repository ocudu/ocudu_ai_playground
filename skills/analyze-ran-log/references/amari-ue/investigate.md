# Amarisoft UE — investigate slot

Type-specific slot for the **investigate** activity. The driving playbook owns
the loop, the Found/Clues/Next block, and the Diagnosis template; this file only
supplies what is specific to this artifact.

## symptom — how to identify things here

- Which run directory and UE component.
- Which UE, by its 4-char hex `UE_ID` in the log (e.g. `0001`, `000a`).
- Approximate timestamp window — from the NAS state timeline or the `stdout.log`
  CBR stats.

Run `overview.md`'s summary script if it hasn't run for this input. Treat the
anomalies it flags as primary leads: packet loss, unexpected final NAS state, PHY
errors, missing `# Ended on`.

## symptom → playbook

Ordered **most-specific first** — take the first row that matches.

| Symptom | Playbook |
|---|---|
| UE attached, HO triggered, then CBR loss spike | `troubleshooting/handover.md` |
| Reestablishment seen / UE disconnected unexpectedly | `troubleshooting/handover.md` — reestablishment is the failure tail of a HO |
| UE attached but no data flow / CBR loss high | `troubleshooting/data-session.md` |
| UE never attached / stuck before 5GMM-REGISTERED | `troubleshooting/registration.md` |
| UE deregistered before the `power_off` sim event | `troubleshooting/registration.md` |

**Coverage gap — don't force these into the table above.** This type has only
three playbooks, and two symptom classes have none:

- **PHY-only failures** (`crc=FAIL`, PRACH sent with no response, no SIB decode).
  `registration.md` does *not* cover these; it assumes the UE got that far. The UE
  log can only show what it transmitted and what it decoded, so the real next step
  is the gNB side: escalate to the `correlate` type and use its radio-link-failure
  trace to establish whether the gNB saw the transmission at all.
- **Radio-link failure without a handover.** Same escalation.

Load the matching playbook and follow its investigation checklist; each cites its
`reference/` sequence sibling for the expected message flow.

## checks specific to this type

- The UE log is the **terminal's** view. A failure here often needs the gNB log or
  a pcap to establish the network-side cause — the UE can only show what it sent
  and what it decoded.
- Compare the sim-event timeline against the NAS timeline: a symptom that precedes
  its triggering sim event (e.g. loss before `cbr_send`) is a different problem
  than one that follows it.
