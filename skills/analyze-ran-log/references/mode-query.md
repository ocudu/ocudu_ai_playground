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

Scope by UE identifier **early** in multi-UE runs — the cross-product over UEs is
large. Ask via `AskUserQuestion` only when scoping is genuinely ambiguous (e.g. a
multi-UE run and the question names no UE → list the candidate RNTIs/UE-IDs from
the inventory first, using the candidate-listing recipe in the type's
`query.md`).

## Phase B — execute

Prefer the type's helper script over a hand-crafted grep/tshark chain. Reuse any
cached output from a prior overview instead of re-running.

Cap output at ~200 lines; spill anything larger to
`<cache-dir>/<type>-query-<sha>.{txt,tsv}` and report the path (see `SKILL.md`
§ Efficiency rules).

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

Only if the session surfaced a reusable recipe — route it per
`references/self-maintenance.md`.
