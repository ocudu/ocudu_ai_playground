# Query mode

Answer one specific question about the run. Classify it as **single-artifact**
(delegate) or **cross-artifact** (correlate here). Stay tight; do not enter the
investigation loop unless asked.

## Phase A — classify and scope

Restate the question in one sentence. Decide:

- **Single-artifact** — the answer lives entirely in one artifact type. Delegate
  to the owning sub-skill via the `Skill` tool, passing the resolved path and the
  question:
  | Question example | Delegate to |
  |---|---|
  | "How many handovers did the gNB do?" | `analyze-ocudu-gnb-log` (query) |
  | "What was the UE's final NAS state?" | `analyze-amari-ue-log` (query) |
  | "How many NGAP UEContextRelease in the pcap?" | `analyze-pcap` (query) |

- **Cross-artifact** — the answer requires lining up ≥2 sources. Run this skill's
  correlation scripts:
  | Question example | Tool |
  |---|---|
  | "Did every PRACH/PUSCH the UE sent reach the gNB?" | `correlate_radio.py --kind pusch` (and `--kind prach`) |
  | "Is the UE↔gNB↔pcap on the same clock?" | `align_clocks.py` |
  | "Trace UE 0003 end to end" | `map_ue_ids.py` + `correlate_radio.py --rnti` + `procedures/attach-end-to-end.md` |
  | "Which UE owns C-RNTI 0x4607 across the logs and pcap?" | `references/ue-identity-map.md` + `map_ue_ids.py` |

Ask via `AskUserQuestion` only when scoping is genuinely ambiguous (e.g. a
multi-UE run and the question names no UE → list candidate RNTIs/UE-IDs from the
inventory).

## Phase B — execute

For cross-artifact questions, anchor on the right key (see
`references/cross-correlation.md`):
- radio events → **(SFN.slot, RNTI)** at the PHY layer (exact);
- UE identity → the Amarisoft UEID / C-RNTI chain (`ue-identity-map.md`);
- CP events / pcap → wall-clock UTC (raw `frame.time_epoch`).

Scope by `--rnti` early in multi-UE runs. Cap output; spill large tables to the
`run-` prefixed cache file and report its path.

## Phase C — answer

- Direct answer first sentence.
- Evidence: the script/sub-skill used, the matched rows (slot, rnti, timestamps,
  frame numbers), and which sources agreed.
- If a single-artifact sub-skill answered it, attribute that and add any
  cross-source caveat (e.g. "the gNB decoded it; the pcap confirms the F1AP
  forward at T+δ").
- If unanswerable from the artifacts, say so and list what was tried.

## Exit criteria

Question answered or marked unanswerable. Don't loop — let the user drive next.

## Persist learnings

If you found a reusable cross-correlation recipe, persist it into
`references/cross-correlation.md` (or a `procedures/*.md`). If the learning is
single-artifact, route it to that sub-skill instead (see SKILL.md § Memory).
