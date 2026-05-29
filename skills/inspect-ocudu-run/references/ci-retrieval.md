# GitLab CI job → local run directory

When the user gives a GitLab CI job URL instead of a local path, fetch and unzip
the artifacts into a local directory first, then continue with the normal flow
(Step 1 onward in SKILL.md). A CI job may contain several independent test runs —
do **not** download artifacts before the user picks one.

## Step 1 — Fetch the raw job log (lightweight)

```bash
curl -fsSL "https://gitlab.com/<group>/<project>/-/jobs/<job_id>/raw" -o /tmp/job.log
# Private project: add  --header "PRIVATE-TOKEN: $GITLAB_TOKEN"   (or use: glab ci ...)
```

## Step 2 — Extract the run list and present it

Strip ANSI codes, then pull the test summary:
```bash
sed 's/\x1b\[[0-9;]*m//g' /tmp/job.log > /tmp/job_clean.log
grep -A200 'short test summary info' /tmp/job_clean.log | grep -E '(FAILED|PASSED|SKIPPED|ERROR) tests/'
```
Retina also emits per-component error/warning summaries — high-value fast signals:
```bash
grep -E 'has [0-9]+ errors|has [0-9]+ warnings' /tmp/job_clean.log | head -20
```
Build a numbered list (status, test name, failure reason) and present it.
**Do not proceed until the user selects a run.**

## Step 3 — Download and unzip the job artifacts

One artifact archive per job (not per test):
```bash
curl -fsSL "https://gitlab.com/<group>/<project>/-/jobs/<job_id>/artifacts/download" \
  -o /tmp/job_artifacts.zip
python3 -m zipfile -e /tmp/job_artifacts.zip /tmp/run_artifacts/
find /tmp/run_artifacts -maxdepth 4 -name testbed.json
```

> Use `python3 -m zipfile`, **not** `unzip`: the `unzip` CLI treats `[...]` in
> paths as shell globs and silently skips entries with brackets — common with
> pytest-parameterized names like `test_gnb[functional.singleue...]`.

## Step 4 — Continue as a local run

Point `run_inventory.py` at the selected test's directory under
`/tmp/run_artifacts/...` and proceed with the chosen mode. The downloaded layout
matches the local layout in `components.md`.
