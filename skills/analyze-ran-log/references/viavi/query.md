# VIAVI — query slot

Type-specific slot for the **query** activity; the driving playbook pulls this
in.

## restate and scope

Identify the `UE Id` (decimal) / event / time window to scope by.

## execute

Use the search script first when it fits:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/viavi/viavi_log_search.py <command-log> \
  [--ue <id>] \
  [--event <substr>] \
  [--after <HH:MM:SS:mmm>] \
  [--before <HH:MM:SS:mmm>] \
  [--pattern <regex>] \
  [--count] \
  [--max-lines 200]
```

| Question | Command |
|---|---|
| "How many UEs registered?" | `--event "NR REGISTRATION IND" --count` |
| "Did any random access fail?" | `--event "Random Access Error" --count` |
| "Show everything for UE 113" | `--ue 113` |
| "When did UE 113 first connect?" | `--ue 113 --event "NR CONNECTION IND"` |
| "Any connection failures?" | `--event "NR CONNECTION FAILED IND"` |
| "Handovers in a time window" | `--event "Handover Complete" --after … --before …` |
| "Did the RUs come up?" | `--pattern "CU PLANE ACTIVE"` |
| "RLC retransmission limit hit?" | `--pattern "maximum retransmissions"` |
| "Any failed tester commands?" | `--pattern "C: [A-Z_]+ 0x(?!00)"` |

`--event` is a **substring** filter on `I: CMPI` lines — use the precise form
(`"NR REGISTRATION IND"`, not `"REGISTRATION IND"`, which also matches
`DEREGISTRATION IND`).

Otherwise use the canonical greps in `reference/log-format.md` § Key grep recipes;
cap with `| head -n 200` and spill larger results to `viavi-query-<sha>.txt`.
