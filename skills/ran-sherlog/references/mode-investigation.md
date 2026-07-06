# Investigation mode

Drive a root-cause investigation **at the cross-artifact level** — pick the next
lead, correlate across sources, and converge. Single-artifact deep dives run via
the relevant `ran-log-reference` type.

## Conduct

- **Confirmed vs hypothesized.** Distinguish the two in every claim. Until a test
  has proven a cause — a correlation that pins the failing side, a spec/source
  lookup, a reproduced signal — it is a **hypothesis**: label it as one and name
  the check that would confirm or refute it. **Never** use definitive language
  ("the investigation is decisive", "this proves it", "the root cause is X") for a
  claim additional tests have not confirmed; prefer "leading hypothesis: X",
  "evidence so far suggests X — confirm with `<check>`". A single suggestive signal
  is a lead, not a conclusion; cross-source correlation raises confidence but still
  name what would break the hypothesis. Definitive wording is earned only after the
  confirming test has run and agreed.
- **Modifying OCUDU source to test a hypothesis.** The source tree is read-only by
  default. The **first time** confirming a hypothesis *requires* a source change (a
  new unit test, or a temporary log line), stop and ask the user for authorization
  before touching anything — offering: edit the `$RAN_LOG_REFERENCE_OCUDU_PATH`
  checkout in place, work in a throwaway git worktree, or no authorization (stay
  read-only). Once granted, it holds for the session. See `ran-log-reference`'s
  `references/ocudu/source-code.md` § Modifying the source.
- **Question-asking.** Ask **after every meaningful finding** (Phase C step 5), not
  after silent intermediate checks. On *Different angle* / *Clarify*, treat the
  reply as new input and re-enter the loop without restating the whole symptom block.

## Phase A — symptom

State the symptom in one short paragraph: which run, which UE (UEID and/or
C-RNTI), expected vs observed, and the approximate time/slot window. Run the
inventory and `correlate/align_clocks.py` first if not already done — a clock/slot
misalignment invalidates every later correlation. (All `correlate/…` paths are
under `ran-log-reference`.)

## Phase B — first hypothesis → a cross-artifact trace

Match the symptom to a cross-artifact procedure trace in `ran-log-reference`'s
`correlate` subtree — attach, handover, radio-link failure, identity mismatch,
no-data / PUSCH-PUCCH — following that skill's own correlate index to the matching
trace and script. Each trace shows the same procedure from the UE log, the gNB
log, and the pcap, and names the join key at each step.

## Phase C — investigation loop

Repeat until diagnosis or the user stops:

1. Pick the **next smallest cross-source check** that confirms or refutes the
   current hypothesis — usually one correlation-script run, one
   `correlate/map_ue_ids.py` pass, one single-artifact query run here with an
   `ran-log-reference` type, or (when the expected behavior or implementation is in
   question) a `spec-explorer` lookup or an OCUDU-source grep. Don't read raw logs.
2. Run it. Apply the efficiency + clock/slot rules.
3. Decide if the result is **meaningful** (locates a failure in time+source,
   confirms/refutes the hypothesis, or opens a lead in another source).
   Intermediate non-results feed silently into the next check.
4. On a meaningful finding, emit:

   ```
   **Found:** <one sentence — source(s), slot/timestamp, the matched evidence>
   **Clues so far:**
     - <bullet>
     - <up to 5 total>
   **Next:** <exact script/type call you intend to run>
   **Why:** <one sentence — which hypothesis this supports or refutes>
   ```

5. Immediately follow with `AskUserQuestion` offering:
   - **Continue** — proceed with the planned **Next**.
   - **Deep-dive a type** — load the `ocudu` / `amari-ue` / `pcap` type and run a
     deep single-artifact dive on the current artifact here, then continue.
   - **Check spec / source** — consult `spec-explorer` for the expected 3GPP
     behavior, or the OCUDU source for the implementation, then continue.
   - **Different angle** *(open text)* — another source, UE, or time window.
   - **Skip to diagnosis** — produce the final diagnosis now.
   - **Clarify** *(open text)* — supply missing context.

6. Act on the choice and loop.

## Phase D — final diagnosis

```
## Diagnosis

- **What worked:** <procedures/sources that were consistent>
- **What failed:** <source, slot/timestamp, the cross-source evidence>
- **Root cause (confirmed | hypothesis):** <one paragraph in NR/5G terms; name the
  failing side — UE TX vs gNB decode vs CN. Mark **confirmed** only if a test
  pinned it; otherwise mark **hypothesis** and give the check that would confirm it>
- **Key evidence:**
  - `<source> <slot/ts> <excerpt>` — <why it matters>
  - <the correlation row that pinned which side failed>
- **Suggested next steps:** <config knob, type deep-dive, spec/source check, re-run variant>
```

State the root cause at its true confidence (see § Conduct above): if
a confirming cross-source test has run and agreed, present it as established;
otherwise present it as the leading **hypothesis** and name the check that would
confirm it. Don't call a diagnosis decisive on one uncorroborated signal.

The unique value here is **attributing the failure to the right side**: e.g.
"gNB PUSCH crc=KO while the UE logged the transmission → the UE did send; the
issue is gNB-side decode / ZMQ alignment, not UE DTX" — a conclusion no single
artifact type can reach (and one to state as confirmed only once the correlation
row actually pins it).

## Phase E — persist learnings

Route per SKILL.md § Memory & self-maintenance: analysis learnings go to
`ran-log-reference`, which decides where they land; session/playbook learnings stay
in this skill's `references/`.
