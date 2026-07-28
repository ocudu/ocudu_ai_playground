# Amarisoft UE — investigate slot

Type-specific part of `references/mode-investigate.md` (which drives the loop, the
Found/Clues/Next block, and the Diagnosis template).

## symptom — how to identify things here

- Which run directory and UE component.
- Which UE, by its 4-char hex `UE_ID` in the log (e.g. `0001`, `000a`).
- Approximate timestamp window — from the NAS state timeline or the `stdout.log`
  CBR stats.

Run `overview.md`'s summary script if it hasn't run for this input. Treat the
anomalies it flags as primary leads: packet loss, unexpected final NAS state, PHY
errors, missing `# Ended on`.

## symptom → playbook

| Symptom | Playbook |
|---|---|
| UE never attached / stuck before 5GMM-REGISTERED | `troubleshooting/registration.md` |
| UE attached but no data flow / CBR loss high | `troubleshooting/data-session.md` |
| UE attached, HO triggered but CBR loss spike | `troubleshooting/handover.md` |
| UE disconnected unexpectedly / reestablishment seen | `troubleshooting/handover.md` |
| UE deregistered before the `power_off` sim event | `troubleshooting/registration.md` |
| PHY failures only (`crc=FAIL`, PRACH not responding) | `troubleshooting/registration.md` |

Load the matching playbook and follow its investigation checklist; each cites its
`reference/` sequence sibling for the expected message flow.

## checks specific to this type

- The UE log is the **terminal's** view. A failure here often needs the gNB log or
  a pcap to establish the network-side cause — the UE can only show what it sent
  and what it decoded.
- Compare the sim-event timeline against the NAS timeline: a symptom that precedes
  its triggering sim event (e.g. loss before `cbr_send`) is a different problem
  than one that follows it.
