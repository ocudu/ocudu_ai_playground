#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
Fetch failed job traces for a GitLab pipeline.

Usage:
    fetch_pipeline.py <url> [-o OUTPUT_DIR] [--token TOKEN]

URL forms accepted:
  https://gitlab.example.com/group/project/-/jobs/<job_id>
  https://gitlab.example.com/group/project/-/pipelines/<pipeline_id>
  https://gitlab.example.com/api/v4/projects/<project_id>/pipeline_schedules/<schedule_id>

Output layout:
  <output_dir>/
    <pipeline_id>/
      data.json           # pipeline metadata (id, url, name, ref, status, ...)
      <job_id>/
        data.json         # job metadata
        trace.txt         # raw job log
"""

import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

# https://gitlab.example.com/group/sub/project/-/jobs/123
# https://gitlab.example.com/group/sub/project/-/pipelines/123
_WEB_URL_RE = re.compile(r"(https?://[^/]+)/(.+?)/-/(jobs|pipelines)/(\d+)/?$")

# Artifact files to download from each failed job (matched against the full artifact path).
_ARTIFACT_PATTERNS: list[re.Pattern] = [
    re.compile(r"Testing/Temporary/MemoryChecker\.[^/]*\.log$"),
    re.compile(r"agent-log[^/]*\.log$"),
    re.compile(r"[^/]*stdout[^/]*\.log$"),
]

# https://gitlab.example.com/api/v4/projects/<project_id>/pipeline_schedules/<schedule_id>
_SCHEDULE_API_RE = re.compile(r"(https?://[^/]+)/api/v4/projects/([^/]+)/pipeline_schedules/(\d+)/?$")


class _Client:
    def __init__(self, base_url: str, token: str = ""):
        self._base = base_url.rstrip("/")
        self._headers = {"PRIVATE-TOKEN": token} if token else {}

    def _get(self, path: str, params: dict | None = None) -> bytes:
        url = f"{self._base}/api/v4/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=self._headers)
        with urllib.request.urlopen(req) as resp:
            return resp.read()

    def _get_json(self, path: str, params: dict | None = None) -> dict | list:
        return json.loads(self._get(path, params).decode())

    def _project_root(self, project: str) -> str:
        encoded = urllib.parse.quote(project, safe="") if "/" in project else project
        return f"projects/{encoded}"

    def job(self, project: str, job_id: int) -> dict:
        return self._get_json(f"{self._project_root(project)}/jobs/{job_id}")

    def pipeline(self, project: str, pipeline_id: int) -> dict:
        return self._get_json(f"{self._project_root(project)}/pipelines/{pipeline_id}")

    def schedule(self, project: str, schedule_id: int) -> dict:
        return self._get_json(f"{self._project_root(project)}/pipeline_schedules/{schedule_id}")

    def latest_scheduled_pipeline(self, project: str, schedule_id: int) -> dict:
        pipelines = self._get_json(
            f"{self._project_root(project)}/pipeline_schedules/{schedule_id}/pipelines",
            {"per_page": 1, "order_by": "id", "sort": "desc"},
        )
        if not pipelines:
            raise ValueError(f"No pipelines found for schedule {schedule_id}")
        return pipelines[0]

    def pipeline_jobs(self, project: str, pipeline_id: int) -> list:
        jobs, page = [], 1
        while True:
            batch = self._get_json(
                f"{self._project_root(project)}/pipelines/{pipeline_id}/jobs",
                {"per_page": 100, "page": page, "include_retried": "false"},
            )
            if not batch:
                break
            jobs.extend(batch)
            page += 1
        return jobs

    def job_trace(self, project: str, job_id: int) -> str:
        return self._get(f"{self._project_root(project)}/jobs/{job_id}/trace").decode(errors="replace")

    def artifacts_zip(self, project: str, job_id: int) -> bytes | None:
        """Download the full artifacts zip. Returns None if no artifacts exist for this job."""
        try:
            return self._get(f"{self._project_root(project)}/jobs/{job_id}/artifacts")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise


def _resolve(client: _Client, raw_url: str, log=print) -> tuple[str, int, dict]:
    """
    Returns (project, pipeline_id, extra_pipeline_fields).
    extra_pipeline_fields carries schedule_description when resolved from a schedule URL.
    """
    url = raw_url.rstrip("/")

    m = _SCHEDULE_API_RE.match(url)
    if m:
        project = m.group(2)
        schedule_id = int(m.group(3))
        log(f"Schedule URL — fetching schedule {schedule_id} ...")
        sched = client.schedule(project, schedule_id)
        log(f"  schedule: {sched.get('description', '')} — resolving latest pipeline ...")
        p = client.latest_scheduled_pipeline(project, schedule_id)
        pipeline_id = p["id"]
        log(f"  latest pipeline: {pipeline_id} ({p.get('web_url', '')})")
        return project, pipeline_id, {"name": sched.get("description", "")}

    m = _WEB_URL_RE.match(url)
    if not m:
        raise ValueError(f"Cannot parse as GitLab job/pipeline/schedule URL: {raw_url!r}")

    project = m.group(2)
    kind = m.group(3)  # "jobs" or "pipelines"
    id_ = int(m.group(4))

    if kind == "jobs":
        log(f"Job URL — fetching job {id_} to resolve pipeline ...")
        job_data = client.job(project, id_)
        pipeline_id = job_data["pipeline"]["id"]
        log(f"  pipeline: {pipeline_id}")
        return project, pipeline_id, {}

    return project, id_, {}


def _extract_matching(zip_bytes: bytes, patterns: list[re.Pattern]) -> list[tuple[str, bytes]]:
    """Return [(path, content)] for every file in the zip whose path matches any pattern."""
    matched = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if any(p.search(name) for p in patterns):
                matched.append((name, zf.read(name)))
    return matched


def _pick(data: dict, *keys) -> dict:
    return {k: data[k] for k in keys if k in data}


def main():
    parser = argparse.ArgumentParser(description="Fetch a GitLab pipeline and failed job traces for triage")
    parser.add_argument("url", help="GitLab job URL, pipeline URL, or schedule API URL")
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("/tmp/triage"),
        help="Root output directory (default: /tmp/triage)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITLAB_TOKEN", ""),
        metavar="TOKEN",
        help="GitLab personal/project access token (default: $GITLAB_TOKEN)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output (stderr). JSON result is always printed to stdout.",
    )
    args = parser.parse_args()

    def log(*msg):
        if not args.quiet:
            print(*msg, file=sys.stderr)

    base_url = re.match(r"https?://[^/]+", args.url)
    if not base_url:
        parser.error(f"Cannot extract base URL from: {args.url!r}")
    client = _Client(base_url.group(), token=args.token)

    try:
        project, pipeline_id, extra = _resolve(client, args.url, log=log)
    except (ValueError, urllib.error.HTTPError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    log(f"Fetching pipeline {pipeline_id} ...")
    pipeline_data = client.pipeline(project, pipeline_id)

    pipeline_dir = args.output_dir / str(pipeline_id)
    pipeline_dir.mkdir(parents=True, exist_ok=True)

    pipeline_json = _pick(pipeline_data, "id", "iid", "name", "ref", "status", "source", "sha",
                          "created_at", "updated_at", "started_at", "finished_at", "web_url",
                          "coverage", "duration")
    pipeline_json.update(extra)
    (pipeline_dir / "data.json").write_text(json.dumps(pipeline_json, indent=2), encoding="utf-8")

    all_jobs = client.pipeline_jobs(project, pipeline_id)
    failed_jobs = [j for j in all_jobs if j.get("status") == "failed"]
    log(f"  {len(all_jobs)} total jobs, {len(failed_jobs)} failed")

    result = {
        "pipeline": pipeline_json,
        "output_dir": str(pipeline_dir),
        "failed_jobs": [],
    }

    for job in failed_jobs:
        job_id = job["id"]
        job_name = job.get("name", str(job_id))
        log(f"  [{job_id}] {job_name} ...")

        job_dir = pipeline_dir / str(job_id)
        job_dir.mkdir(exist_ok=True)

        job_json = _pick(job, "id", "name", "status", "stage", "ref", "duration",
                         "queued_duration", "created_at", "started_at", "finished_at",
                         "web_url", "tag", "allow_failure")
        (job_dir / "data.json").write_text(json.dumps(job_json, indent=2), encoding="utf-8")

        job_entry = {**job_json, "trace": None, "artifacts": []}

        try:
            trace = client.job_trace(project, job_id)
            trace_path = job_dir / "trace.txt"
            trace_path.write_text(trace, encoding="utf-8", errors="replace")
            job_entry["trace"] = str(trace_path)
            log(f"    trace: {len(trace):,} bytes")
        except urllib.error.HTTPError as exc:
            log(f"    trace: skipped ({exc})")

        if _ARTIFACT_PATTERNS:
            zip_bytes = client.artifacts_zip(project, job_id)
            if zip_bytes:
                for artifact_path, content in _extract_matching(zip_bytes, _ARTIFACT_PATTERNS):
                    dest = job_dir / "artifacts" / artifact_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(content)
                    job_entry["artifacts"].append(str(dest))
                    log(f"    artifact: {artifact_path}")

        result["failed_jobs"].append(job_entry)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
