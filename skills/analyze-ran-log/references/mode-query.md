# Query mode

Answer one specific question about the run. Classify it as **single-artifact**
(delegate) or **cross-artifact** (correlate here). Stay tight; do not enter the
investigation loop unless asked.

## Phase A — classify and scope

Restate the question in one sentence. Decide:

- **Single-artifact** — the answer lives entirely in one artifact type. Use the
  owning type (loaded via the `Skill` tool), then answer here
  using its search script (follow its `references/<type>/analysis-guide.md`
  § Answering a targeted question):
  | Question example | Type |
  |---|---|
  | "How many handovers did the gNB do?" | `ocudu` |
  | "What was the UE's final NAS state?" | `amari-ue` |
  | "How many NGAP UEContextRelease in the pcap?" | `pcap` |

- **Cross-artifact** — the answer requires lining up ≥2 sources. Use
  the `correlate` subtree (scripts under `scripts/correlate/`,
  references under `references/correlate/`):
  | Question example | Tool |
  |---|---|
  | "Did every PRACH/PUSCH the UE sent reach the gNB?" | `correlate/correlate_radio.py --kind pusch` (and `--kind prach`) |
  | "Is the UE↔gNB↔pcap on the same clock?" | `correlate/align_clocks.py` |
  | "Trace UE 0003 end to end" | `correlate/map_ue_ids.py` + `correlate/correlate_radio.py --rnti`, guided by the attach trace in the `correlate` subtree |
  | "Which UE owns C-RNTI 0x4607 across the logs and pcap?" | `correlate/map_ue_ids.py`, guided by the identity model in the `correlate` subtree |

Ask via `AskUserQuestion` only when scoping is genuinely ambiguous (e.g. a
multi-UE run and the question names no UE → list candidate RNTIs/UE-IDs from the
inventory).

## Phase B — execute

For cross-artifact questions, anchor on the right key (the clock/key model lives in
the `correlate` subtree):
- radio events → **(SFN.slot, RNTI)** at the PHY layer (exact);
- UE identity → the Amarisoft UEID / C-RNTI chain (its correlate identity model);
- CP events / pcap → wall-clock UTC (raw `frame.time_epoch`).

Scope by `--rnti` early in multi-UE runs. Cap output; spill large tables to the
`correlate-` prefixed cache file and report its path.

## Phase C — answer

- Direct answer first sentence.
- Evidence: the script/type used, the matched rows (slot, rnti, timestamps,
  frame numbers), and which sources agreed.
- If a single-artifact type answered it, attribute that and add any cross-source
  caveat (e.g. "the gNB decoded it; the pcap confirms the F1AP forward at T+δ").
- If unanswerable from the artifacts, say so and list what was tried.

## Exit criteria

Question answered or marked unanswerable. Don't loop — let the user drive next.

## Persist learnings

If you found a reusable cross-correlation recipe, persist it into this skill's
`correlate` subtree (route per its self-maintenance). If the learning is
single-artifact, route it to that type instead (see SKILL.md § Memory).
