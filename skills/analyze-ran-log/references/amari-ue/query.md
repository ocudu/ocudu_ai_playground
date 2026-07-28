# Amarisoft UE — query slot

Type-specific slot for the **query** activity; the driving playbook pulls this
in.

## restate and scope

Identify:

- Which file(s) to search (`ue.log`, `stdout.log`, `amarisoft_ue.cfg`).
- Which grep pattern or script flag answers it.
- Whether to scope by UE ID or cell ID.

Candidate-listing recipe when scope is ambiguous — UE IDs are 4-char hex. The
summary script already names the UEs that never reached 5GMM-REGISTERED, so prefer
its Anomalies block; to enumerate all of them:

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
| "What was the final NAS state?" | `--layer NAS` then tail |
| "Did the UE reestablish?" | `--pattern "reestablishment" --layer RRC` |
| "What band/BW was used?" | read `amarisoft_ue.cfg` (fields: `reference/config-format.md`) or `grep "^RF" stdout.log` |

Regex alternation can't be written inside a markdown table cell, so these live
here — copy them verbatim, the pipe must **not** be backslash-escaped:

```bash
grep -aE "CBR_RECV|CBR_SEND" stdout.log     # packet loss / throughput
grep -aE "^# (Started|Ended)" ue.log        # run duration
```

Otherwise use targeted grep with the canonical recipes in
`reference/log-format.md` § Key grep recipes. Cap with `| head -n 200`; if larger,
narrow (time window, UE ID) or spill to `amari-query-<sha>.txt`.
