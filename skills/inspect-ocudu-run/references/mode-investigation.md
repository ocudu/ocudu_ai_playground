# Investigation mode

Drive a root-cause investigation **at the cross-artifact level**. Single-artifact
deep dives are delegated to the sub-skills; this skill's job is to pick the next
lead, correlate across sources, and converge. After every meaningful finding,
share clues + next step + why, then ask the user to confirm or redirect.

## Phase A — symptom

State the symptom in one short paragraph: which run, which UE (UEID and/or
C-RNTI), expected vs observed, and the approximate time/slot window. Run the
inventory and `align_clocks.py` first if not already done — a clock/slot
misalignment invalidates every later correlation.

## Phase B — first hypothesis → a cross-artifact trace

Match the symptom to a cross-artifact procedure:

| Symptom | Trace file |
|---|---|
| UE never attached / stuck before RRC setup | `procedures/attach-end-to-end.md` |
| UE attached but no/!data; PUSCH or PUCCH issues | `procedures/attach-end-to-end.md` + `correlate_radio.py` |
| Handover failed / UE went to wrong cell | `procedures/handover-end-to-end.md` |
| UE dropped / RLF / reestablishment | `procedures/radio-link-failure.md` |
| Counts disagree across UE / gNB / pcap | `references/ue-identity-map.md` (identity joining) |

Each trace shows the same procedure from the UE log, the gNB log, and the pcap,
and names the join key at each step.

## Phase C — investigation loop

Repeat until diagnosis or the user stops:

1. Pick the **next smallest cross-source check** that confirms or refutes the
   current hypothesis — usually one correlation-script run, one `map_ue_ids.py`
   pass, or one delegated sub-skill query. Don't read raw logs.
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
   **Next:** <exact script/sub-skill call you intend to run>
   **Why:** <one sentence — which hypothesis this supports or refutes>
   ```

5. Immediately follow with `AskUserQuestion` offering:
   - **Continue** — proceed with the planned **Next**.
   - **Delegate to sub-skill X** — hand the current artifact to
     `analyze-ocudu-gnb-log` / `analyze-amari-ue-log` / `analyze-pcap` for a deep
     single-artifact dive, then resume here with its result.
   - **Different angle** *(open text)* — another source, UE, or time window.
   - **Skip to diagnosis** — produce the final diagnosis now.
   - **Clarify** *(open text)* — supply missing context.

6. Act on the choice and loop.

## Phase D — final diagnosis

```
## Diagnosis

- **What worked:** <procedures/sources that were consistent>
- **What failed:** <source, slot/timestamp, the cross-source evidence>
- **Root cause:** <one paragraph in NR/5G terms; name the failing side —
  UE TX vs gNB decode vs CN — established by the cross-source correlation>
- **Key evidence:**
  - `<source> <slot/ts> <excerpt>` — <why it matters>
  - <the correlation row that pinned which side failed>
- **Suggested next steps:** <config knob, sub-skill deep-dive, re-run variant>
```

The unique value here is **attributing the failure to the right side**: e.g.
"gNB PUSCH crc=KO while the UE logged the transmission → the UE did send; the
issue is gNB-side decode / ZMQ alignment, not UE DTX" — a conclusion no single
sub-skill can reach.

## Phase E — persist learnings

Route per the SKILL.md § Memory rule: cross-correlation learnings stay here
(propose into `cross-correlation.md` or a `procedures/*.md`); artifact-specific
learnings are proposed into the owning sub-skill. Propose → confirm → apply.

## Question-asking discipline

- Ask **after every meaningful finding** (Phase C step 5), not after silent
  intermediate checks.
- On *Different angle* / *Clarify*, treat the reply as new input and re-enter the
  loop without restating the whole symptom block.
