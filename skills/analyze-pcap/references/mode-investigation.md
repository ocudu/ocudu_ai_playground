# Investigation mode

Drive a root-cause investigation. After every meaningful finding, share clues
+ next planned check + the reason, and ask the user to confirm or redirect.

## Phase A — symptom

Establish the symptom in one short paragraph:

- Which pcap(s) and which run directory.
- Which UE (if known) and how it's identified (C-RNTI, AMF-UE-NGAP-ID, …).
- Which event(s) appear missing or erroneous.
- Approximate timestamp window.

If `pcap_overview.py` has not already been run for this input, run it now to
establish the activity baseline. Treat anomalies it flagged (Failures,
Rejects, unbalanced setup/release counts) as primary leads.

## Phase B — first hypothesis

Pick the most likely matching procedure from `references/procedures/`:

- `random-access.md` — PRACH not detected, UE stuck before RRC Setup, Msg3
  failures.
- `registration.md` — InitialUEMessage without InitialContextSetupResponse,
  AMF rejections.
- `pdu-session-setup.md` — PDU Session Resource Setup Failure, zero throughput
  with UE attached.
- `handover.md` — HandoverPreparation / HandoverCommand / UEContextSetup on
  target, CFRA / CBRA on target cell, re-establishment after HO.
- `ue-context-release.md` — unexpected UEContextReleaseCommand, cause IE
  values pointing at RLF or AMF-initiated release.

Load that file and follow its expected-sequence checklist.

## Phase C — investigation loop

Repeat until diagnosis or the user asks to stop:

1. Pick the next check (one tshark filter or one helper script call). Bias
   toward the smallest check that can refute the current hypothesis.
2. Run it. Apply the efficiency rules from SKILL.md.
3. Decide whether the result is **meaningful**. A finding is meaningful when:
   - It locates a specific failure event in time and protocol, OR
   - It refutes or supports the current hypothesis, OR
   - It opens a lead into a different protocol or UE.
   Intermediate filter results that don't change the picture stay silent —
   just feed into the next check.
4. On a meaningful finding, emit this block:

   ```
   **Found:** <one sentence — protocol, file, epoch, frame#, what it shows>
   **Clues so far:**
     - <bullet>
     - <bullet>
     - <up to 5 total>
   **Next:** <exact tshark filter or script invocation you intend to run>
   **Why:** <one sentence — which hypothesis this supports or refutes>
   ```

5. Immediately follow with `AskUserQuestion` offering:
   - **Continue** — proceed with the planned **Next**.
   - **Different angle** *(open text)* — redirect to another protocol, UE, or
     timestamp.
   - **Skip to diagnosis** — stop collecting; produce the final diagnosis from
     what you have.
   - **Ask clarification** *(open text)* — supply missing context (which UE,
     expected behaviour, what changed since the last good run).

6. Act on the user's choice and loop.

## Phase D — final diagnosis

When the user picks **Skip to diagnosis**, or when the hypothesis is supported
to your satisfaction, produce a single closing block:

```
## Diagnosis
- Working: <what completed normally>
- Failed: <what failed, with protocol + epoch + frame#>
- Root cause (protocol-level): <one paragraph in 5G/NR terms>
- Cross-references:
  - Sibling pcap evidence: <ngap.pcap frame N, f1ap.pcap frame M …>
  - Log lines to correlate: <suggested grep patterns for the matching .log>
- Suggested next steps: <which pcap / log to look at next; what to enable>
```

## Phase E — persist learnings

For every generalisable insight discovered during the investigation, append to
the appropriate file (see SKILL.md § Memory).

## Question-asking discipline

- Investigation mode asks **after every meaningful finding** (Phase C step 5).
- It does **not** ask after intermediate filters that didn't change the
  picture.
- If the user redirects via *Different angle* or *Ask clarification*, treat the
  reply as new input and re-enter the loop without restating the whole
  symptom block.
