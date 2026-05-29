# Investigation mode

Drive a root-cause investigation of an OCUDU gNB run. After every meaningful
finding, share clues + next planned check + the reason, then ask the user to
confirm or redirect.

## Phase A — symptom

Establish the symptom in one short paragraph:

- Which run directory and component (`ocudu-gnb-*` vs `ocudu-cu-*` vs `ocudu-du-*`).
- Which UE (if known) and how it's identified — `ue=N` on CU side, or the
  `c-rnti=0xNNNN` on the DU side, or `amf_ue_ngap_id` on the AMF/NGAP side.
- What the expected behaviour was vs. what was observed.
- Approximate timestamp window (from the procedure timeline produced by the
  summary script, or from `[METRICS]` rows, or from the user).

If the summary script has not been run yet for this input, run it now:

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/ocudu_log_summary.py <run-dir>
```

Treat anomalies it flagged (warnings/errors, late HARQs, NGAP setup failure,
RRC reestablishment, msg3 NACKs, abnormal shutdown, dropped traffic) as
primary leads.

## Phase B — first hypothesis

Match the symptom to the most likely procedure file:

| Symptom | File |
|---|---|
| UE never attached (no `UE created` or no `Initial Context Setup Routine finished`) | `procedures/ue-attach.md` |
| UE attached but no data / DRB never set up | `procedures/pdu-session-setup.md` |
| Handover triggered but failed (no `rrcReconfigurationComplete` on target, or RLF after `reconfigurationWithSync`) | `procedures/handover.md` |
| RRC reestablishment seen (`rrcReestablishmentRequest`) | `procedures/reestablishment.md` |
| UE released unexpectedly | `procedures/ue-release.md` |
| NGAP / AMF connection lost or never established | `procedures/ngap-setup.md` |
| PHY-only failures (PRACH undecoded, persistent `crc=FAIL`, ZMQ rx waiting) | `procedures/phy-issues.md` |
| Throughput regression / late HARQs / failed PDCCH | `procedures/throughput-degradation.md` |
| Process crashed / abnormal exit | `procedures/abnormal-exit.md` |

Load the matching file and follow its expected-sequence checklist.

If no procedure file matches, fall back to the layered approach:
1. Identify the **last successful** layer-level event before the symptom.
2. Identify the **first divergent** event after it.
3. The gap is your hypothesis space.

## Phase C — investigation loop

Repeat until diagnosis or the user asks to stop:

1. Pick the **next smallest check** that can confirm or refute the current
   hypothesis. Use grep or the search script — never read raw `gnb.log` into
   context.
2. Run it. Apply the efficiency rules from `SKILL.md`.
3. Decide whether the result is **meaningful**:
   - Locates a specific failure event in time and layer, OR
   - Confirms or refutes the current hypothesis, OR
   - Opens a new lead in a different layer, UE, or peer component.
   Intermediate results that don't change the picture: feed them silently into
   the next check, don't emit anything.
4. On a **meaningful** finding, emit this block:

   ```
   **Found:** <one sentence — layer, timestamp, log line excerpt, what it shows>
   **Clues so far:**
     - <bullet>
     - <bullet>
     - <up to 5 total>
   **Next:** <exact grep/script command you intend to run>
   **Why:** <one sentence — which hypothesis this supports or refutes>
   ```

5. Immediately follow with `AskUserQuestion` offering:
   - **Continue** — proceed with the planned **Next**.
   - **Different angle** *(open text)* — redirect to another layer, UE, or
     time window, or jump to a sibling artifact (the UE log via
     `analyze-amari-ue-log`, a PCAP via `analyze-pcap`).
   - **Skip to diagnosis** — stop collecting; produce the final diagnosis now.
   - **Clarify** *(open text)* — supply missing context (expected outcome,
     config changes, related ticket, etc.).

6. Act on the user's choice and loop.

## Cross-artifact escalation

When the symptom is on the UE side or on the air interface, the OCUDU log
alone is insufficient. Offer to:

- Hand off to **`analyze-amari-ue-log`** if a sibling `amarisoft-ue-*/`
  directory exists for this test — the UE-side log shows MIB/SIB decoding,
  PRACH transmission, RRC state machine.
- Hand off to **`analyze-pcap`** if any sibling `*.pcap` exists in the same
  run dir — F1AP/E1AP/NGAP body details are richer in pcap.

Make the offer when current clues plateau, not before.

## Phase D — final diagnosis

When the user picks **Skip to diagnosis**, or when the hypothesis is confirmed,
produce a single closing block:

```
## Diagnosis

- **What worked:** <procedures that completed normally>
- **What failed:** <layer, timestamp, log line excerpt>
- **Root cause:** <one paragraph in NR/5G protocol terms, naming the specific
  message / counter / config knob>
- **Key log evidence:**
  - `<timestamp> [LAYER] <excerpt>` (line N) — <why it matters>
  - ...
- **Suggested next steps:**
  - <which sibling artifact to cross-correlate (UE log, PCAP, AMF log)>
  - <which config knob to tune, which test variant to re-run>
```

## Phase E — persist learnings

If the investigation surfaced a generalisable learning (a reusable grep
recipe, a new failure signature, a log/config detail), persist it via the
flow in `SKILL.md` § Memory & self-maintenance — propose it, confirm, then
weave it into the natural section (or create a new procedure/script file if
warranted).

## Question-asking discipline

- Investigation mode asks **after every meaningful finding** (Phase C step 5).
- It does **not** ask after intermediate searches that didn't change the picture.
- If the user redirects via *Different angle* or *Clarify*, treat the reply as
  new input and re-enter the loop without restating the whole symptom block.
- It is always preferable to ask than to silently widen scope or jump layers.
