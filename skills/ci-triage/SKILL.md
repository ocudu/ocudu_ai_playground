---
description: Triage failed jobs in a GitLab CI pipeline — classify each failure and match it to known issues in the ocudu group. Use when given a GitLab pipeline, job, or schedule URL.
argument-hint: <gitlab-pipeline-or-job-url>
arguments: [url]
allowed-tools: Bash, Read
---

# CI Job Failure Triage

**Usage:** `/ci-triage <gitlab-job-url-or-pipeline-url>`

Triage all failed jobs in a GitLab CI pipeline. For each failure, classify it and find the best matching issue in the `gitlab.com/ocudu` group. Output is a single summary table.

> **Tool constraint:** Use the fetch script for pipeline and job data. Use `glab` CLI for issue queries. Never use `curl`, `wget`, or direct HTTP calls.

---

## Step 1 — Fetch pipeline data and issues in parallel

Run both simultaneously — they are independent:

**Fetch pipeline data:**

```!
python3 ~/.claude/commands/ci-triage/scripts/fetch_pipeline.py --quiet "$url"
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
glab api '/groups/ocudu/issues?labels=bug%3A%3Aci&state=opened&per_page=100'
```

Keep this list in context — it is reused for every job without further API calls.

## Step 2 — Analyze each failed job

Process each job from `failed_jobs` in turn.

### 2a — Read job log

**Expected failure formats** — identify which tool failed from the trace and parse accordingly:

- **make** — compiler or linker error: `error:` lines with file/line, or `ld:` errors
- **ctest / GoogleTest** — `[  FAILED  ] TestSuite.TestName`, assertion lines (`EXPECT_*/ASSERT_*`), or exception messages
- **pytest (Retina E2E)** — `FAILED tests/<file>.py::<test_name>[<suite.param>]` lines; may also have a Pass/Fail Criteria table and per-component log sections

Start with the tail of the **script** section — strip `after_script` first (it only contains cleanup/artifact upload noise):

```bash
awk '/section_start.*after_script/{exit} {print}' "<job.trace>" | tail -n 200
```

If the tail surfaces test names or error markers, grep for all failures and for context around each one:

```bash
# All failure lines with line numbers
grep -n "FAILED\|\[  FAILED  \]\|error:\|Error:" "<job.trace>"

# Context around a specific test or error
grep -n -A 20 "<test_name_or_error>" "<job.trace>"
```

Only read the full trace if the tail and greps are inconclusive.

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

**Tier 1 — open `bug::ci` issues** (match client-side against the pre-fetched list, no API call):

- **High**: suite name or exact error phrase in the issue **title**
- **Medium**: key error phrase or component name in the issue **description**

Within each confidence tier, sort by `updated_at` descending — issues not updated in a long time are less likely to be the active cause of the current failure.

**Tier 2 — all open issues, keyword search** (only if Tier 1 yields no High match):

```bash
glab api '/groups/ocudu/issues?state=opened&per_page=30&search=KEYWORD'
```

**Tier 3 — closed `bug::ci` issues, keyword search** (only if Tiers 1–2 yield no match at all):

```bash
glab api '/groups/ocudu/issues?labels=bug%3A%3Aci&state=closed&per_page=30&search=KEYWORD'
```

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

## Step 4 — Generate MD

Copy the generated table into a markdown file. Add a h2 item with format: `## [pipeline_id](url) (ref, date)`
