# Query mode (playbook)

Answer one specific question about the artifact(s). Stay tight; **do not** enter
the investigation loop unless asked.

Generic mechanics live here; the per-type specifics (search-script flags, the
question→command table, which files to search) live in
`references/<kind>/query.md`.

## Phase A — classify and scope

Restate the question in one sentence, then decide:

- **Single-artifact** — the answer lives entirely in one artifact type. Read
  `references/<kind>/query.md` and use its search script / recipes.

  | Question example | Kind |
  |---|---|
  | "How many handovers did the gNB do?" | `ocudu` |
  | "What was the UE's final NAS state?" | `amari-ue` |
  | "How many NGAP UEContextRelease in the pcap?" | `pcap` |
  | "Did any random access fail on the tester?" | `viavi` |

- **Cross-artifact** — the answer requires lining up ≥2 sources. Read
  `references/correlate/query.md`, which owns the cross-artifact question→script
  table and the join-key model.

Ask via `AskUserQuestion` only when scoping is genuinely ambiguous (e.g. a
multi-UE run and the question names no UE) — and list the candidate RNTIs/UE-IDs
first, using the candidate-listing recipe in the type's `query.md`, so the choice
is concrete.

## Phase B — execute

Prefer the type's helper script over a hand-crafted grep/tshark chain, and scope
before you widen — narrow by UE and time window first, then relax if the answer
isn't there. A query returning nothing is evidence of **absence** only once you've
confirmed the scope was right; until then it's evidence of a bad filter.

## Phase C — answer

- **Direct answer in the first sentence.**
- Evidence: the script/filter used, and the matched rows — timestamps, line
  numbers, frame numbers, slot/RNTI, whichever the type keys on.
- If a single type answered it, attribute that, and add any cross-source caveat
  worth stating (e.g. "the gNB decoded it; the pcap confirms the F1AP forward at
  T+δ").
- If unanswerable from the artifacts, say so and list what was tried.

## Exit criteria

Question answered or marked unanswerable. **Don't loop** — let the user drive
what's next. If the answer itself exposes a failure worth chasing, say so in one
sentence and offer `mode-investigate.md`; don't start investigating unprompted.

## Persist learnings

Only if generalisable — route per `references/self-maintenance.md`.
