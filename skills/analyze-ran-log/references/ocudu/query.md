# OCUDU — query slot

Type-specific slot for the **query** activity; the driving playbook pulls this
in.

## restate and scope

Identify:

- Which file(s) to search (`gnb.log`, `stdout.log`, `ocudu_gnb.yml`,
  `metrics.json`).
- Which grep pattern or script flag answers it.
- Whether to scope by UE (`ue=N` on the CU side, `c-rnti=0xNNNN` on the DU side)
  or by cell (`pci=N`).

Candidate-listing recipes when scope is ambiguous:

```bash
grep -oE 'ue=[0-9]+ c-rnti=0x[0-9a-f]{4}: UE created' gnb.log | sort -u   # UEs
grep -oE 'pci=[0-9]+' gnb.log | sort -u                                   # cells
```

## execute

Use the search script first when it fits:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu/ocudu_log_search.py <gnb.log> \
  [--layer <exact tag>] \
  [--ue <N>] \
  [--rnti <hex>] \
  [--pci <N>] \
  [--after <HH:MM:SS.mmm>] \
  [--before <HH:MM:SS.mmm>] \
  [--pattern <regex>] \
  [--level <regex over D|I|W|E|C>] \
  [--count] \
  [--max-lines 200]
```

`--layer` is an **exact** tag match, not a substring — pass a tag that really
appears in the log. There is **no `F1AP` or `E1AP` tag**; F1AP/E1AP traffic is
split by endpoint. The full set (`reference/log-format.md` § Layer tags):

```
ALL CONFIG GNB RRC NGAP SCTP-GW PDCP SDAP SEC MAC SCHED PHY FAPI METRICS
CU-CP CU-CP-F1 CU-CP-E1 CU-UEMNG CU-UP CU-UP-E1 CU-F1-U
DU DU-F1 DU-F1-U DU-MNG GTPU UDP-GW IO-EPOLL
```

| Question | Command |
|---|---|
| "How many handovers?" | `--pattern reconfigurationWithSync --count` |
| "When did the UE attach?" | `--layer RRC --pattern "DCCH UL rrcSetupComplete"` |
| "All PRACH events" | `--layer SCHED --pattern "prach\("` |
| "Cells configured?" | `--pattern "Cell creation idx="` |
| "Final RRC release?" | `--layer RRC --pattern "rrcRelease"` |
| "Bearer setups?" | `--pattern "BearerContextSetupResponse" --count` |
| "Which band/BW used?" | read `ocudu_gnb.yml` or `grep "^Cell pci=" stdout.log` |
| "Did the UE complete attach?" | `--layer CU-CP --pattern '"Initial Context Setup Routine" finished'` |
| "Reestablishment seen?" | `--pattern "rrcReestablishment"` |
| "UE's first RRC msg across F1?" | `--layer CU-CP-F1 --pattern "InitialULRRCMessageTransfer"` |

Regex alternation can't be written inside a markdown table cell, so these live
here — copy them verbatim, the pipe must **not** be backslash-escaped:

```bash
--pattern "NGSetupResponse|NGSetupFailure"              # NGAP connect to AMF
--pattern "Built in|Workers stopped successfully"       # run duration
--level "E|W|C"                                         # errors and warnings
```

Otherwise use targeted grep with the canonical recipes in
`reference/log-format.md` § Key grep recipes. Cap with `| head -n 200`; if larger,
narrow (time window, UE id, cell) or spill to `ocudu-query-<sha>.txt`.

**YAML/config questions** — look at **both** `ocudu_gnb.yml` (what the
user/Retina supplied; search top-to-bottom because of duplicate-key, last-wins
behaviour) **and** the `[CONFIG  ] [D] Input configuration` echo at the top of
`gnb.log` (the effective value after defaults and merges). Mention both if they
differ.

**Metrics questions** — for "max throughput", "BLER", "any late HARQs", parse
`metrics.json` with python; never `cat` it whole. The summary script already does
the common rollups — prefer it.

## answer shape

```
**Answer:** The UE attached at 18:18:30.803 (gnb.log:758).

Evidence:
  18:18:30.803 [RRC] DCCH UL rrcSetupComplete           (line 758)
  18:18:30.952 [CU-CP] "Initial Context Setup Routine" finished successfully (line 890)

Commands used:
  grep -nE "DCCH UL rrcSetupComplete|Initial Context Setup Routine.*finished" gnb.log
```
