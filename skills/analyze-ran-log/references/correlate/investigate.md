# correlate — investigate slot

Type-specific slot for the **investigate** activity. The driving playbook owns the
loop, the Found/Clues/Next block, and the Diagnosis template; this file supplies
only what is specific here. This is the whole-run altitude, where the goal is
**attributing the failure to the right side**.

## symptom — how to identify things here

- Which run, and which components are present.
- Which UE, by the identifier that survives the whole trace: the Amarisoft **UEID**
  (stable) rather than the C-RNTI (changes on handover). See `ue-identity-map.md`.
- The approximate time **and slot** window.

**Run the alignment step first** (`overview.md` § clock / slot alignment). A clock
or slot misalignment invalidates every later correlation, so this is not optional —
a "missing" event is frequently just a misaligned one.

## symptom → cross-artifact trace

| Symptom | Trace |
|---|---|
| UE never attached, or attached on one side only | `procedures/attach-end-to-end.md` |
| Handover triggered but the UE never landed on the target | `procedures/handover-end-to-end.md` |
| UE dropped / reestablished — which side failed? | `procedures/radio-link-failure.md` |
| UE identity mismatch between sources (counts or IDs disagree) | `ue-identity-map.md` |
| No user-plane data despite an attached UE (PUSCH/PUCCH) | `procedures/radio-link-failure.md` + `correlate_radio.py --kind pusch` |

Each trace shows the same procedure from the UE log, the gNB log, and the pcap,
and names the join key at each step. Work it hop by hop: the first hop where the
sources **disagree** localises the failure.

## checks specific to this type

- **Attribute, don't just observe.** The characteristic finding here has the form
  "source A shows X, source B does not, therefore the failure is on side B" — a
  conclusion no single type can reach. Make that the shape of every finding.
- A missing event on one side has three explanations, and they need different next
  checks: it was never generated, it was generated but not captured, or the join
  key was wrong. Rule out the third first (it's the cheapest).
- When a correlation needs one side's parsing detail, load that per-artifact
  subtree in addition (`../ocudu/investigate.md`, `../amari-ue/investigate.md`,
  `../pcap/investigate.md`) — this type may reach into the siblings it joins.
- Off-host sources (VIAVI, remote 5GC) carry a real clock offset that **nothing
  measures automatically** — `align_clocks.py` does not check them. Never treat a
  wall-clock gap involving them as evidence: join on a clock-independent key
  instead (`(SFN.slot, RNTI)`, or the VIAVI TC-RNTI bridge in
  `ue-identity-map.md`), or derive Δ by hand from one such pair first and say so.
