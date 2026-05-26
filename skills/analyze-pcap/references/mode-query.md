# Query mode

Answer one specific question about the capture. Stay tight; do not enter the
investigation loop unless the user asks for it.

## Phase A — restate

Restate the question in one sentence and identify the smallest filter that
answers it: which pcap, which display filter, which fields.

Ask via `AskUserQuestion` **only** when scoping is ambiguous, for example:

- The pcap has multiple UEs and the question doesn't pin one → offer the
  list of `ran_ue_ngap_id` values plus an open-text option.
- The question references a time window not present in the question → offer
  candidate windows (first 30 s, the full capture, around a specific event).

When scope is clear, proceed without asking.

## Phase B — execute

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

## Phase C — answer

Reply concisely:

- Direct answer first sentence.
- Supporting evidence: frame number(s), epoch timestamp(s), the exact tshark
  filter you used.
- If relevant, the corresponding event in a sibling pcap (e.g. NGAP
  InitialContextSetupRequest at epoch T paired with the F1AP UEContextSetup
  at T+δ).
- If the question is unanswerable from the capture, say so and list what you
  tried.

## Exit criteria

Question answered or marked unanswerable. Do not loop or solicit more
questions — let the user drive the next request.

## Persist learnings

Append to `references/tshark-recipes.md` only when:
- A filter you wrote is non-obvious *and* likely to be reused.
- A dissector field name turned out to be different from what
  `references/protocols/<proto>.md` documents — in that case, fix the
  protocol file too.
