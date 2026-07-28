# Amarisoft UE — query slot

Type-specific slot for the **query** activity; the driving playbook pulls this
in.

## restate and scope

Identify:

- Which file(s) to search (`ue.log`, `stdout.log`, `amarisoft_ue.cfg`).
- Which grep pattern or script flag answers it.
- Whether to scope by UE ID or cell ID.

Candidate-listing recipe when scope is ambiguous — UE IDs are 4-char hex:

```bash
grep -oE ' [0-9a-f]{4} New state' ue.log | sort -u
```

## execute

Use the search script first when it fits:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/amari-ue/ue_log_search.py <ue.log> \
  [--layer <NAS|RRC|PHY|MAC|PROD>] \
  [--ue <ue_id>] \
  [--cell <cell_id>] \
  [--after <HH:MM:SS.mmm>] \
  [--before <HH:MM:SS.mmm>] \
  [--pattern <regex>] \
  [--count] \
  [--max-lines 200]
```

| Question | Command |
|---|---|
| "How many handovers?" | `--pattern reconfigurationWithSync --count` |
| "When did UE attach?" | `--layer NAS --pattern "REGISTERED\s+CM-CONNECTED"` |
| "All PRACH attempts" | `--layer PHY --pattern "PRACH:"` |
| "What cells did the UE see?" | `--layer PHY --pattern "PSS:"` |
| "Was there packet loss?" | grep `CBR_RECV\|CBR_SEND` in `stdout.log` |
| "What was the final NAS state?" | `--layer NAS` then tail |
| "Did the UE reestablish?" | `--pattern "reestablishment" --layer RRC` |
| "What band/BW was used?" | read `amarisoft_ue.cfg` (fields: `reference/config-format.md`) or `grep "^RF" stdout.log` |
| "How long did the run last?" | `grep -E "^# (Started\|Ended)" ue.log` |

Otherwise use targeted grep with the canonical recipes in
`reference/log-format.md` § Key grep recipes. Cap with `| head -n 200`; if larger,
narrow (time window, UE ID) or spill to `amari-query-<sha>.txt`.
