# Query mode

Answer one specific question about the UE run. Stay tight; do not enter the
investigation loop unless the user explicitly asks for it.

## Phase A — restate and scope

Restate the question in one sentence. Identify:
- Which file(s) to search (`ue.log`, `stdout.log`, `amarisoft_ue.cfg`).
- Which grep pattern or script flag answers it.
- Whether scoping by UE ID or cell ID is needed.

Ask via `AskUserQuestion` **only** when scoping is genuinely ambiguous:
- Multi-UE run and the question does not pin one UE → list the UE IDs (hex) with
  `grep -oE ' [0-9a-f]{4} New state' ue.log | sort -u`.
- Time window needed but not specified → offer candidate windows derived
  from NAS state transitions.

When scope is clear, proceed without asking.

## Phase B — execute

### Use the search script first when it fits

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/ue_log_search.py <ue.log> \
  [--layer <NAS|RRC|PHY|MAC|PROD>] \
  [--ue <ue_id>] \
  [--cell <cell_id>] \
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
| "When did UE attach?" | `--layer NAS --pattern "REGISTERED CM-CONNECTED"` |
| "All PRACH attempts" | `--layer PHY --pattern "PRACH:"` |
| "What cells did the UE see?" | `--layer PHY --pattern "PSS:"` |
| "Was there packet loss?" | grep `CBR_RECV\|CBR_SEND` in `stdout.log` |
| "What was the final NAS state?" | `--layer NAS` then tail |
| "Did the UE reestablish?" | `--pattern "reestablishment" --layer RRC` |
| "What band/BW was used?" | read `amarisoft_ue.cfg` or `grep "^RF" stdout.log` |
| "How long did the run last?" | `grep "^# (Started\|Ended)" ue.log` |

### Otherwise, use targeted grep

Use the canonical recipes in `references/log-format.md` § Key grep recipes.
Always cap with `| head -n 200`; if a result is larger, narrow it (time window,
UE ID) or spill to `/tmp/amari-ue-query.txt` and report the path.

## Phase C — answer

Reply concisely:

- Direct answer first sentence.
- Supporting evidence: log line number(s), timestamp(s), the grep/script used.
- If unanswerable from the available files, say so and list what was tried.

## Exit criteria

Question answered or marked unanswerable. Do not loop or solicit more questions —
let the user drive the next request.

## Persist learnings

If you wrote a non-obvious, reusable grep/script combination, or found a log field
documented incorrectly, persist the fix via `SKILL.md` § Memory & self-maintenance
(propose → confirm → integrate into the natural section, e.g. § Key grep recipes or
the relevant format table).
