# Investigation mode

Drive a root-cause investigation. After every meaningful finding, share clues +
next planned check + the reason, then ask the user to confirm or redirect.

## Phase A — symptom

Establish the symptom in one short paragraph:

- Which run directory and UE component.
- Which UE ID (if known) and how it's identified (4-char hex UE_ID in log, e.g. `0001`, `000a`).
- What the expected behaviour was vs. what was observed.
- Approximate timestamp window (from NAS state timeline or stdout CBR stats).

If the summary script has not been run yet for this input, run it now:

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/ue_log_summary.py <run-dir>
```

Treat anomalies it flagged (packet loss, unexpected final NAS state, PHY errors,
missing `# Ended on`) as primary leads.

## Phase B — first hypothesis

Match the symptom to the most likely procedure from `references/procedures/`:

| Symptom | File |
|---|---|
| UE never attached / stuck before 5GMM-REGISTERED | `procedures/registration.md` |
| UE attached but no data flow / CBR loss high | `procedures/data-session.md` |
| UE attached, HO triggered but CBR loss spike | `procedures/handover.md` |
| UE disconnected unexpectedly / reestablishment seen | `procedures/handover.md` |
| UE deregistered before `power_off` sim event | `procedures/registration.md` |
| PHY failures only (crc=FAIL, PRACH not responding) | `procedures/registration.md` |

Load the matching file and follow its expected-sequence checklist.

## Phase C — investigation loop

Repeat until diagnosis or the user asks to stop:

1. Pick the **next smallest check** that can confirm or refute the current
   hypothesis. Use grep or the search script — never read raw log into context.
2. Run it. Apply the efficiency rules from `SKILL.md`.
3. Decide whether the result is **meaningful**:
   - Locates a specific failure event in time and layer, OR
   - Confirms or refutes the current hypothesis, OR
   - Opens a new lead in a different layer or UE.
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
   - **Different angle** *(open text)* — redirect to another layer, UE, or time window.
   - **Skip to diagnosis** — stop collecting; produce the final diagnosis now.
   - **Clarify** *(open text)* — supply missing context (expected outcome, config changes, etc.).

6. Act on the user's choice and loop.

## Phase D — final diagnosis

When the user picks **Skip to diagnosis**, or when the hypothesis is confirmed,
produce a single closing block:

```
## Diagnosis

- **What worked:** <procedures that completed normally>
- **What failed:** <layer, timestamp, log line excerpt>
- **Root cause:** <one paragraph in NR/5G protocol terms>
- **Key log evidence:**
  - `<timestamp> [LAYER] <excerpt>` — <why it matters>
  - ...
- **Suggested next steps:**
  - <which log/pcap to cross-correlate; what to enable in the config>
```

## Phase E — persist learnings

If the investigation surfaced a generalisable learning (a reusable grep recipe, a
new failure signature, a log/format detail), persist it via the flow in `SKILL.md`
§ Memory & self-maintenance — propose it, confirm, then weave it into the natural
section (or create a new procedure/script file if warranted).

## Question-asking discipline

- Investigation mode asks **after every meaningful finding** (Phase C step 5).
- It does **not** ask after intermediate searches that didn't change the picture.
- If the user redirects via *Different angle* or *Clarify*, treat the reply as
  new input and re-enter the loop without restating the whole symptom block.
