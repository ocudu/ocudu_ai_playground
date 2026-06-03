#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
Query GitLab group issues.

Usage:
    query_issues.py --group GROUP [options]

Always prints to stdout:
    {"issues": [...], "total": <count>}

Authentication: $GITLAB_TOKEN env var or --token.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _api_get(base_url: str, path: str, token: str, params: dict | None = None) -> object:
    url = f"{base_url}/api/v4/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = {"PRIVATE-TOKEN": token} if token else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"ERROR: HTTP {exc.code} fetching {url}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"ERROR: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def _fetch_all_pages(base_url: str, path: str, token: str, params: dict) -> list:
    results, page = [], 1
    while True:
        batch = _api_get(base_url, path, token, {**params, "page": page, "per_page": 100})
        if not isinstance(batch, list) or not batch:
            break
        results.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Query GitLab group issues")
    parser.add_argument("--group", required=True, help="Group path, e.g. ocudu")
    parser.add_argument("--state", default="opened", choices=["opened", "closed", "all"])
    parser.add_argument("--labels", default="", help="Comma-separated labels, e.g. 'bug::ci'")
    parser.add_argument("--search", default="", help="Keyword search in title and description")
    parser.add_argument(
        "--per-page", type=int, default=100,
        help="Max results for a single-page query (default 100). Ignored when --all-pages is set.",
    )
    parser.add_argument(
        "--all-pages", action="store_true",
        help="Paginate until all results are fetched.",
    )
    parser.add_argument(
        "--base-url", default="https://gitlab.com",
        help="GitLab instance URL (default: https://gitlab.com)",
    )
    parser.add_argument(
        "--token", default=os.environ.get("GITLAB_TOKEN", ""),
        help="Personal access token (default: $GITLAB_TOKEN)",
    )
    args = parser.parse_args()

    path = f"groups/{urllib.parse.quote(args.group, safe='')}/issues"
    params: dict = {"state": args.state}
    if args.labels:
        params["labels"] = args.labels
    if args.search:
        params["search"] = args.search

    if args.all_pages:
        issues = _fetch_all_pages(args.base_url, path, args.token, params)
    else:
        issues = _api_get(args.base_url, path, args.token, {**params, "per_page": args.per_page})
        if not isinstance(issues, list):
            issues = []

    print(json.dumps({"issues": issues, "total": len(issues)}, indent=2))


if __name__ == "__main__":
    main()
