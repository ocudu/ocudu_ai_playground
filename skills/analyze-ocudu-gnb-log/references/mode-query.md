# Query mode

Answer one specific question about the OCUDU gNB run. Stay tight; do not enter
the investigation loop unless the user explicitly asks for it.

## Phase A — restate and scope

Restate the question in one sentence. Identify:
- Which file(s) to search (`gnb.log`, `stdout.log`, `ocudu_gnb.yml`,
  `metrics.json`).
- Which grep pattern or script flag answers it.
- Whether scoping by UE (`ue=N` on CU side, `c-rnti=0xNNNN` on DU side) or by
  cell (`pci=N`) is needed.

Ask via `AskUserQuestion` **only** when scoping is genuinely ambiguous:
- Multi-UE run and the question does not pin one UE → list the UEs:
  `grep -oE 'ue=[0-9]+ c-rnti=0x[0-9a-f]{4}: UE created' gnb.log | sort -u`.
- Multi-cell run and the question does not pin one cell → list PCIs:
  `grep -oE 'pci=[0-9]+' gnb.log | sort -u`.
- Time window needed but not specified → offer candidate windows
  (UE create → UE release; gNB start → AMF connected; first PRACH → SIB1; etc.).

When scope is clear, proceed without asking.

## Phase B — execute

### Use the search script first when it fits

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/ocudu_log_search.py <gnb.log> \
  [--layer <RRC|NGAP|F1AP|E1AP|MAC|SCHED|PHY|PDCP|CU-CP|CU-UP|DU|...>] \
  [--ue <N>] \
  [--rnti <hex>] \
  [--pci <N>] \
  [--after <HH:MM:SS.mmm>] \
  [--before <HH:MM:SS.mmm>] \
  [--pattern <regex>] \
  [--count] \
  [--max-lines 200]
```

Examples for common questions:

| Question | Command |
|---|---|
| "How many handovers?" | `--pattern reconfigurationWithSync --count` |
| "When did the UE attach?" | `--layer RRC --pattern "DCCH UL rrcSetupComplete"` |
| "When did NGAP connect to AMF?" | `--pattern "NGSetupResponse\|NGSetupFailure"` |
| "All PRACH events" | `--layer SCHED --pattern "prach\("` |
| "Cells configured?" | `--pattern "Cell creation idx="` |
| "Final RRC release?" | `--layer RRC --pattern "rrcRelease"` |
| "Bearer setups?" | `--pattern "BearerContextSetupResponse" --count` |
| "Which band/BW used?" | read `ocudu_gnb.yml` or `grep "^Cell pci=" stdout.log` |
| "How long did the run last?" | `--pattern "Built in\|Workers stopped successfully"` |
| "Any errors or warnings?" | `--level "E\|W\|C"` |
| "Did the UE complete attach?" | `--layer CU-CP --pattern '"Initial Context Setup Routine" finished'` |
| "Reestablishment seen?" | `--pattern "rrcReestablishment"` |

### Otherwise, use targeted grep

Use the canonical recipes in `references/log-format.md` § Key grep recipes.
Always cap with `| head -n 200`; if a result is larger, narrow it (time window,
UE id, cell) or spill into the session cache dir as
`${CLAUDE_CODE_TMPDIR:-/tmp}/claude-skills-${CLAUDE_CODE_SESSION_ID}/gnb-query-<sha>.txt`
and report the path (see SKILL.md § Efficiency rules).

### YAML/config questions

For questions about config values, look at **both**:

1. `ocudu_gnb.yml` — what the user/Retina supplied (search top-to-bottom because
   of the duplicate-key, last-wins behaviour).
2. The `[CONFIG  ] [D] Input configuration` echo at the top of `gnb.log` —
   the effective value after defaults and merges.

Mention both if they differ (e.g. user requested `all_level: warning`, but a
later block reset it to `info`).

### Metrics questions

For "max throughput", "BLER", "any late HARQs", etc., parse `metrics.json`
with python — never `cat` it whole. Example one-liner:

```bash
python3 -c '
import json
recs = json.load(open("metrics.json"))   # metrics.json is a JSON array
peak_dl = max((u["dl_brate"] for r in recs if "cells" in r for c in r["cells"] for u in c.get("ue_list", [])), default=0)
print(f"peak DL brate (per UE) = {peak_dl/1e6:.2f} Mbps")
'
```

The summary script does the common rollups already — prefer it.

## Phase C — answer

Reply concisely:

- Direct answer in the first sentence.
- Supporting evidence: log line number(s), timestamp(s), the grep/script used.
- If unanswerable from the available files, say so and list what was tried.

Example:

```
**Answer:** The UE attached at 18:18:30.803 (gnb.log:758).

Evidence:
  18:18:30.803 [RRC] DCCH UL rrcSetupComplete           (line 758)
  18:18:30.952 [CU-CP] "Initial Context Setup Routine" finished successfully (line 890)

Commands used:
  grep -nE "DCCH UL rrcSetupComplete|Initial Context Setup Routine.*finished" gnb.log
```

## Exit criteria

Question answered or marked unanswerable. Do not loop or solicit more
questions — let the user drive the next request.

## Persist learnings

If you wrote a non-obvious, reusable grep/script combination, or found a log
field documented incorrectly, persist the fix via `SKILL.md` § Memory &
self-maintenance (propose → confirm → integrate into the natural section, e.g.
§ Key grep recipes or the relevant format table).
