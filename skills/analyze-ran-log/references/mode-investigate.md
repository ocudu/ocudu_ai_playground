# Investigation mode (playbook — the detective)

Drive a root-cause investigation: pick the next lead, run the smallest check that
moves it, and converge. This is the **generic** loop for every artifact type and
altitude; the per-type specifics (which identifiers name a UE, which symptom maps
to which troubleshooting playbook) live in `references/<kind>/investigate.md`.

## Conduct

- **Confirmed vs hypothesized.** Distinguish the two in every claim. Until a test
  has proven a cause — a correlation that pins the failing side, a spec/source
  lookup, a reproduced signal — it is a **hypothesis**: label it as one and name
  the check that would confirm or refute it. **Never** use definitive language
  ("the investigation is decisive", "this proves it", "the root cause is X") for a
  claim additional tests have not confirmed; prefer "leading hypothesis: X",
  "evidence so far suggests X — confirm with `<check>`". A single suggestive signal
  is a lead, not a conclusion; cross-source correlation raises confidence but
  still name what would break the hypothesis. Definitive wording is earned only
  after the confirming test has run and agreed.
- **Never** read a raw log or pcap into context. Use the type's search/summary
  scripts and reuse cached output from any prior overview.
- **Modifying OCUDU source to test a hypothesis.** The source tree is read-only by
  default. The **first time** confirming a hypothesis *requires* a source change
  (a new unit test, or a temporary log line), stop and ask the user for
  authorization before touching anything — offering: edit the
  `$ANALYZE_RAN_LOG_OCUDU_PATH` checkout in place, work in a throwaway git
  worktree, or no authorization (stay read-only). Once granted, it holds for the
  session. See `references/ocudu/source-code.md` § Modifying the source.
- **Question-asking.** Ask **after every meaningful finding** (Phase C step 5),
  not after silent intermediate checks. On *Different angle* / *Clarify*, treat
  the reply as new input and re-enter the loop without restating the whole
  symptom block.

## Phase A — symptom

State the symptom in one short paragraph: which artifact(s)/run, which UE and how
it's identified, expected vs observed, and the approximate time/slot window. The
type's `investigate.md` § symptom names the right identifier for that artifact
(`ue=N` vs `c-rnti=0xNNNN` vs a 4-hex UE_ID vs a decimal `UE Id`).

If the type's summary script hasn't run for this input yet, run it now
(`references/<kind>/overview.md` names it) and treat the anomalies it flags as
primary leads.

At the **whole-run** altitude, also run the clock/slot alignment step in
`references/correlate/overview.md` first — a misalignment invalidates every later
correlation.

## Phase B — first hypothesis

Read `references/<kind>/investigate.md` and use its **symptom → playbook**
dispatch table to pick the matching `troubleshooting/*.md` (failure markers +
investigation checklist). Each playbook cites the expected message sequence in its
`reference/` sibling — compare observed against expected.

At the whole-run altitude, `references/correlate/investigate.md` instead maps the
symptom to a cross-artifact procedure trace, which shows the same procedure from
each source and names the join key at each step.

If no dispatch row matches, fall back to the layered approach:

1. Identify the **last successful** event before the symptom.
2. Identify the **first divergent** event after it.
3. The gap is your hypothesis space.

## Phase C — investigation loop

Repeat until diagnosis or the user stops:

1. Pick the **next smallest check** that confirms or refutes the current
   hypothesis. Prefer the type's scripts and summarized metrics over raw reads.
   When the *expected* behaviour or the *implementation* is in question, do a
   `spec-explorer` or OCUDU-source lookup (`SKILL.md` § Other sources).
2. Run it.
3. Decide whether the result is **meaningful**:
   - it locates a specific failure event in time and layer/protocol/source, **or**
   - it confirms or refutes the current hypothesis, **or**
   - it opens a lead in another layer, UE, or source.

   Intermediate non-results feed **silently** into the next check — don't narrate
   them.
4. On a meaningful finding, emit:

   ```
   **Found:** <one sentence — source(s), layer/protocol, timestamp or slot/frame, the matched evidence>
   **Clues so far:**
     - <bullet>
     - <up to 5 total>
   **Next:** <the exact script/filter/grep you intend to run>
   **Why:** <one sentence — which hypothesis this supports or refutes>
   ```

5. Immediately follow with `AskUserQuestion` offering:
   - **Continue** — proceed with the planned **Next**.
   - **Deep-dive a type** — load another type's subtree and dive on that artifact,
     then continue.
   - **Check spec / source** — consult `spec-explorer` for the expected 3GPP
     behaviour, or the OCUDU source for the implementation, then continue.
   - **Different angle** *(open text)* — another source, UE, or time window.
   - **Skip to diagnosis** — produce the final diagnosis now.
   - **Clarify** *(open text)* — supply missing context.

6. Act on the choice and loop.

## Escalating beyond one artifact

When the symptom points at another side of the interface, one artifact is
insufficient — widen, but only **when clues plateau, not before**:

- a sibling `amarisoft-ue-*/` exists → the `amari-ue` type shows MIB/SIB decode,
  PRACH transmission, the UE RRC/NAS state machine.
- a sibling `*.pcap` exists → the `pcap` type has richer F1AP/E1AP/NGAP bodies.
- ≥2 components exist → `references/correlate/investigate.md` for the
  cross-artifact trace. This is what attributes the failure to the **right side**.
- behaviour depends on the implementation → the OCUDU source
  (`references/ocudu/source-code.md`).

## Phase D — final diagnosis

```
## Diagnosis

- **What worked:** <procedures/sources that were consistent>
- **What failed:** <source, layer/protocol, timestamp or slot/frame, the evidence>
- **Root cause (confirmed | hypothesis):** <one paragraph in NR/5G terms, naming
  the specific message / counter / config knob. At the whole-run altitude, name
  the failing side — UE TX vs gNB decode vs CN. Mark **confirmed** only if a test
  pinned it; otherwise mark **hypothesis** and give the check that would confirm>
- **Key evidence:**
  - `<source> <timestamp|slot|frame#> <excerpt>` — <why it matters>
  - <the correlation row that pinned which side failed, if cross-artifact>
- **Suggested next steps:** <config knob, type deep-dive, spec/source check,
  re-run variant, which sibling artifact to cross-correlate>
```

State the root cause at its true confidence (§ Conduct): if a confirming test has
run and agreed, present it as established; otherwise present it as the leading
**hypothesis** and name the check that would confirm it. Don't call a diagnosis
decisive on one uncorroborated signal.

At the whole-run altitude the unique value is **attributing the failure to the
right side** — e.g. "gNB PUSCH `crc=KO` while the UE logged the transmission → the
UE did send; the issue is gNB-side decode / ZMQ alignment, not UE DTX" — a
conclusion no single artifact type can reach, and one to state as confirmed only
once the correlation row actually pins it.

## Phase E — persist learnings

Only if the session surfaced something generalisable — route it per
`references/self-maintenance.md`. Never persist the run-specific verdict.
