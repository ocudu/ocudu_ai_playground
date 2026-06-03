---
name: ci-triage
description: >
  Triage failed jobs in a GitLab CI pipeline — classify each failure and match it
  to known issues in the ocudu group. Use when given a GitLab pipeline, job, or
  schedule URL. Trigger phrases include: "triage this pipeline", "triage this job",
  "why did this CI job fail", "what failed in this pipeline", "investigate this
  CI failure", "check this run", or any GitLab URL containing /pipelines/ or
  /-/jobs/ under gitlab.com/ocudu.
argument-hint: <gitlab-pipeline-or-job-url>
arguments: [url]
version: 0.1.0
user-invocable: true
context: inline
license: BSD-3-Clause-Open-MPI
compatibility: Requires python3 (stdlib only) and jq. Set GITLAB_TOKEN to a personal access token with api scope for gitlab.com/ocudu.
allowed-tools: Bash(python3 *ci-triage*), Bash(jq *), Read(/tmp/triage/*), Write(/tmp/triage/*)
---

# CI Job Failure Triage

**Usage:** `/ci-triage <gitlab-job-url-or-pipeline-url>`

Triage all failed jobs in a GitLab CI pipeline. For each failure, classify it and find the best matching issue in the `gitlab.com/ocudu` group. Output is a single summary table.

> **Prerequisites:** `python3` (stdlib only), `jq`. Set `GITLAB_TOKEN` to a personal access token with `api` scope for gitlab.com/ocudu.

> **Tool constraint:**
> - **`/tmp/triage/` paths**: use the `Read` tool exclusively. Never run any bash command (`cat`, `wc`, `ls`, `find`, `jq`, `awk`, `grep`, `tail`, or anything else) on paths under `/tmp/triage/` — every new job directory triggers a permission prompt.
> - **Pipeline/job data**: run `fetch_pipeline.py`; its JSON is the tool result — already in context.
> - **Issue queries**: run `query_issues.py`; its JSON is the tool result — read `.issues` directly in context, do not post-process with any shell command.
> - **`jq`**: only for processing piped script output, e.g. `python3 .../query_issues.py ... | jq '.issues[].title'`. Never point `jq` at a file path.
> - Never use `curl`, `wget`, `glab`, or direct HTTP calls. Never use inline `python3 -c`.

---

## Step 1 — Fetch pipeline data and issues in parallel

Run both simultaneously — they are independent:

**Fetch pipeline data:**

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/fetch_pipeline.py --quiet "$url"
```

The script accepts job URLs, pipeline URLs, and schedule API URLs. It resolves everything to a pipeline, downloads traces and matching artifact logs for all failed jobs, and returns a JSON with this shape:

```json
{
  "pipeline": { "id": 123, "name": "...", "ref": "main", "web_url": "...", "status": "failed", ... },
  "output_dir": "/tmp/triage/123",
  "failed_jobs": [
    {
      "id": 456, "name": "unit_tests", "stage": "test", "web_url": "...", "allow_failure": false,
      "trace": "/tmp/triage/123/456/trace.txt",
      "artifacts": ["/tmp/triage/123/456/artifacts/Testing/Temporary/MemoryChecker.1.log"]
    }
  ]
}
```

If `failed_jobs` is empty, report "No failed jobs in this pipeline" and stop.

**Fetch all open `bug::ci` issues:**

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query_issues.py --group ocudu --labels "bug::ci" --state opened
```

Returns `{"issues": [...], "total": N}`. Keep the `issues` array in context — it is reused for every job without further API calls.

## Step 2 — Analyze each failed job

Process each job from `failed_jobs` in turn.

### 2a — Read job log

**Expected failure formats** — identify which tool failed from the trace and parse accordingly:

- **make** — compiler or linker error: `error:` lines with file/line, or `ld:` errors
- **ctest / GoogleTest** — `[  FAILED  ] TestSuite.TestName`, assertion lines (`EXPECT_*/ASSERT_*`), or exception messages
- **pytest (Retina E2E)** — `FAILED tests/<file>.py::<test_name>[<suite.param>]` lines; may also have a Pass/Fail Criteria table and per-component log sections

Use the `Read` tool on `job.trace`. Start with the last 200 lines:

```
Read(file=job.trace, offset=-200)
```

When reading, ignore everything after any line containing `section_start` and `after_script` — that section is only cleanup/artifact upload noise.

If the tail surfaces test names or error markers, read more context around them:

```
Read(file=job.trace, offset=<line_number-10>, limit=40)
```

Read the full trace only if the tail is inconclusive.

### 2b — Extract failure details

For each failure found, extract:

1. **Test ID** — test node ID (`tests/file.py::name[param]`), GoogleTest name (`Suite.Test`), or failing make target
2. **Key error** — the most specific diagnostic line (assertion message, compiler error, exception)
3. **Error type** — one of: `build | crash | assertion | timeout | setup | criteria`

**ctest extras** — if a test failed, check `job.artifacts` for a `MemoryChecker.<N>.log` file. Each file maps to a test by index (matching the ctest run order) and contains the Valgrind memory error trace for that test.

**pytest (Retina E2E) extras** — see [REFERENCE.md](REFERENCE.md) for artifact layout and test suite structure docs:

- Suite param (e.g. `mobility.inter_du_ho.fr1_fr2`) — primary search key
- Pass/Fail Criteria table — which criteria failed and by how much
- `[WARNING]`/`[ERROR]` lines from per-test gnb/ue/5gc log sections (match to the right test)

**If the log shows "Emergency flush of the logger":** never the root cause — the gNB crashed upstream of it. Read the downloaded artifact logs from `job.artifacts` in this order — `agent-log*.log` first (structured gNB log; look for the assertion, segfault, or exception), then `*stdout*.log` (raw process output; useful if the agent-log was lost before the crash was recorded).

### 2c — Derive search keywords (2–4 per failure)

- Suite name or fragments (e.g. `inter_du_ho`, `cfra`, `singleue`)
- Error phrase substrings (e.g. `AMF connection refused`, `Intra CU Handover Target`)
- Component labels (e.g. `CU-CP`, `open5gs`, `SMF`)
- Failed criterion name (e.g. `Handovers`, `DL KOs`)

### 2d — Match against issues

**Tier 1 — open `bug::ci` issues** (in-context match, no command):

The issues list from Step 1 is already in your context window. Scan it mentally — do not run any shell command. Look for:

- **High**: suite name or exact error phrase in the issue **title**
- **Medium**: key error phrase or component name in the issue **description**

Within each confidence tier, prefer issues with a more recent `updated_at`.

**Tier 2 — all open issues, keyword search** (only if Tier 1 yields no High match):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query_issues.py --group ocudu --state opened --search "KEYWORD" --per-page 30
```

**Tier 3 — closed `bug::ci` issues, keyword search** (only if Tiers 1–2 yield no match at all):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query_issues.py --group ocudu --labels "bug::ci" --state closed --search "KEYWORD" --per-page 30
```

All three commands return `{"issues": [...], "total": N}` — read the `issues` array.

Collect the **top 3 candidates** per test, ranked by confidence (High > Medium > Low), then by tier (open bug::ci > open > closed).

## Step 3 — Output: pipeline triage table

Print a single table. Before rendering, **group rows that share the same High-confidence matched issue** into one row — list all affected jobs and tests together in their cells. `Check` and `No match` rows are never grouped and remain one row per test.

**Columns:**

- **Issue(s)** — matched issue link, or top 2–3 candidates with confidence tag for Check rows
- **Verdict** — `Matched` / `Check` / `No match`
- **Job(s)** — job name(s) as link(s); comma-separated if grouped
- **Test(s)** — suite param(s) or test node ID(s); comma-separated if grouped
- **Key failure** — one-line error summary (use the most representative message if grouped)

**Verdict values:**

- **Matched** — High-confidence match; failure is already tracked
- **Check** — Medium or Low match(es); manually confirm before closing
- **No match** — no existing issue found; new issue needed

## Step 4 — Generate MD (optional)

If the `Write` tool is available, write the output to `/tmp/triage/<pipeline_id>.md`:

1. A h2 header: `## [pipeline_id](url) (ref, date)`
2. The triage table from Step 3

If the write is denied, skip silently — the table is already in the response above.
