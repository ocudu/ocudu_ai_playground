# pcap analysis guide

Methodology for the three common pcap-analysis activities. This is reference
knowledge for whoever holds the context (a higher-level inspect/run orchestrator
skill or a direct user session) — pick the section that matches the task. It assumes the
input has already been resolved and preflighted (see `SKILL.md` §§ Step 1–2) and
that the § Efficiency rules apply throughout.

---

## Producing an overview

Produce a quick factual summary of the capture without diving into individual
packets.

### capinfos roll-up

For each input pcap:

```bash
capinfos -aeu <file.pcap>
```

Collect: packet count, capture duration, earliest and latest packet times.
If a run directory was provided, run this for all 5 sibling pcaps.

### per-protocol scan

Run the overview helper:

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/pcap_overview.py <pcap-or-dir> --top 5
```

This emits, per pcap:

- packet count
- first and last `frame.time_epoch`
- distinct UE identifiers (per-protocol fields, see `references/protocols/general.md`)
- top procedure codes (NGAP/F1AP/E1AP) or PDU types (MAC/RLC)
- count of `Failure` / `Reject` / `Release with cause` PDUs

### sibling roll-up (run directory only)

If the input was a run dir, additionally produce:

- NGAP procedures observed, with counts (e.g. `InitialContextSetup x N`,
  `PDUSessionResourceSetup x M`, `UEContextRelease x K`).
- F1AP UE contexts created and released.
- E1AP bearer contexts created and released.
- Time-aligned headline: first NGAP packet, first F1AP packet, last release,
  capture span.

### summary block

Present the collected output as one block:

- Input path (single pcap or run directory).
- One line per pcap: packets, time range, top procedure codes, failure count
  (i.e. the `pcap_overview.py` output verbatim — don't paraphrase).
- For a run dir: a one-line activity headline (UE counts per protocol, total
  setup/release procedures observed) drawn from the sibling roll-up.
- Anomalies bulleted last, one bullet each — non-zero failure counts,
  unbalanced setup/release, sibling pcaps with non-overlapping time ranges.

---

## Answering a targeted question

Answer one specific question about the capture. Stay tight.

### restate and scope

Restate the question in one sentence and identify the smallest filter that
answers it: which pcap, which display filter, which fields. If scope is
genuinely ambiguous (e.g. a multi-UE capture and the question pins no UE), the
caller should clarify scope before running broad queries.

### execute

Use the helper scripts first when one fits the question:

- "what NGAP procedures did UE X go through?" →
  `ngap_procedures.py <ngap.pcap> --ue <ran_ue_id>`
- "how many F1AP / NGAP / E1AP messages of each type?" →
  `extract_proc_codes.py <pcap> --proto <ngap|f1ap|e1ap>`
- "what happened around epoch T across all 5 pcaps?" →
  `correlate_run.py <run-dir> --around <epoch> --window-ms 2000`
- "which F1AP / NGAP / E1AP UEs are in this capture?" →
  `f1ap_ue_ids.py <f1ap.pcap>`, `ngap_ue_ids.py <ngap.pcap>`,
  `e1ap_ue_ids.py <e1ap.pcap>` (each requires the specific protocol pcap)

Otherwise, hand-craft a minimal `tshark` filter:

```bash
tshark -r <file.pcap> \
  -Y '<display filter>' \
  -T fields -t ad -E separator=$'\t' \
  -e frame.number -e frame.time_epoch -e <protocol fields…> \
  | head -n 200
```

If the result exceeds 200 rows, narrow further (add a `frame.time_epoch >= X &&
<= Y` clause, restrict to one UE, restrict to one procedure code) or run it
through a helper script that produces a compact summary.

### answer

Reply concisely:

- Direct answer first sentence.
- Supporting evidence: frame number(s), epoch timestamp(s), the exact tshark
  filter you used.
- If relevant, the corresponding event in a sibling pcap (e.g. NGAP
  InitialContextSetupRequest at epoch T paired with the F1AP UEContextSetup
  at T+δ).
- If the question is unanswerable from the capture, say so and list what you
  tried.

---

## Investigating a failure

Drive a root-cause investigation.

### symptom

Establish the symptom in one short paragraph:

- Which pcap(s) and which run directory.
- Which UE (if known) and how it's identified (C-RNTI, AMF-UE-NGAP-ID, …).
- Which event(s) appear missing or erroneous.
- Approximate timestamp window.

If `pcap_overview.py` has not already been run for this input, run it now to
establish the activity baseline. Treat anomalies it flagged (Failures,
Rejects, unbalanced setup/release counts) as primary leads.

### first hypothesis — procedure dispatch

Pick the most likely matching procedure from `references/procedures/`:

| Symptom | File |
|---|---|
| PRACH not detected, UE stuck before RRC Setup, Msg3 failures | `random-access.md` |
| InitialUEMessage without InitialContextSetupResponse, AMF rejections | `registration.md` |
| PDU Session Resource Setup Failure, zero throughput with UE attached | `pdu-session-setup.md` |
| HandoverPreparation / HandoverCommand / UEContextSetup on target, CFRA / CBRA on target cell, re-establishment after HO | `handover.md` |
| unexpected UEContextReleaseCommand, cause IE pointing at RLF or AMF-initiated release | `ue-context-release.md` |

Load that file and follow its expected-sequence checklist.

### investigation loop

Repeat until the diagnosis is clear:

1. Pick the next check (one tshark filter or one helper script call). Bias
   toward the smallest check that can refute the current hypothesis.
2. Run it. Apply the efficiency rules from `SKILL.md`.
3. Decide whether the result is **meaningful**. A finding is meaningful when:
   - It locates a specific failure event in time and protocol, OR
   - It refutes or supports the current hypothesis, OR
   - It opens a lead into a different protocol or UE.
   Intermediate filter results that don't change the picture just feed into the
   next check.
4. On a meaningful finding, record it as:

   ```
   **Found:** <one sentence — protocol, file, epoch, frame#, what it shows>
   **Clues so far:**
     - <bullet>
     - <up to 5 total>
   **Next:** <exact tshark filter or script invocation you intend to run>
   **Why:** <one sentence — which hypothesis this supports or refutes>
   ```

### final diagnosis

When the hypothesis is supported to your satisfaction, produce a single closing
block:

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

---

## Persisting learnings

If an activity surfaces a generalisable learning (a reusable tshark filter, a
corrected dissector field, a new failure signature), persist it via the flow in
`SKILL.md` § Memory & self-maintenance — weave it into the natural section, or
create a new procedure/script file if warranted.
