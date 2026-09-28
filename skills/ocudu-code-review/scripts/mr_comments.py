#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""mr_comments.py — Digest the human review threads of a GitLab merge request.

Reads the MR's discussions through `glab`, drops system notes (branch changes,
commit pushes, label edits), and emits one compact line per thread plus a full
transcript on disk, so a review can tell what reviewers already said instead of
repeating it.

Usage:
  mr_comments.py --project <path> --iid <n> --out <file> [--max <n>]

Options:
  --project <path>  Project path, `ocudu/ocudu` or percent-encoded.
  --iid <n>         Merge-request iid.
  --out <file>      Where to write the full transcript.
  --max <n>         Compact lines to print. Default: 40.

Prints on stdout, unresolved threads first:
  COMMENT=[resolved] <path>:<line> @<author>: <body>[ (+N replies)]
  COMMENTS_FILE=<path>
  COMMENTS_MORE=<n>       only when threads exceeded --max

Exit status: 0 with output, 0 silently when the MR has no human comments,
2 when glab could not answer.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PAGE_SIZE = 100
MAX_PAGES = 5
BODY_CHARS = 220


def fail(message):
    print(f"mr_comments: {message}", file=sys.stderr)
    sys.exit(2)


def fetch_discussions(project, iid):
    """Every discussion of the MR, following pagination."""
    encoded = project if "%2F" in project else project.replace("/", "%2F")
    discussions = []
    for page in range(1, MAX_PAGES + 1):
        endpoint = (
            f"projects/{encoded}/merge_requests/{iid}/discussions"
            f"?per_page={PAGE_SIZE}&page={page}"
        )
        try:
            result = subprocess.run(
                ["glab", "api", endpoint], capture_output=True, text=True,
            )
        except FileNotFoundError:
            fail("glab is not installed")
        if result.returncode != 0:
            fail(f"glab api failed: {result.stderr.strip() or result.returncode}")
        try:
            batch = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            fail("glab returned no usable JSON")
        if not isinstance(batch, list):
            fail("glab returned no usable JSON")
        discussions.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
    return discussions


def anchor(note):
    """`path:line` the note hangs off, or an empty string for a general note."""
    position = note.get("position") or {}
    path = position.get("new_path") or position.get("old_path")
    if not path:
        return ""
    line = position.get("new_line") or position.get("old_line")
    return f"{path}:{line}" if line else path


def one_line(body):
    return re.sub(r"\s+", " ", (body or "").strip())


def digest(discussions):
    """Human threads, unresolved first, each as a dict of what to show."""
    threads = []
    for discussion in discussions:
        notes = [n for n in discussion.get("notes", []) if not n.get("system")]
        if not notes:
            continue
        head = notes[0]
        threads.append({
            "resolved": any(n.get("resolved") for n in notes),
            "where": anchor(head),
            "author": (head.get("author") or {}).get("username", "?"),
            "body": (head.get("body") or "").strip(),
            "replies": [
                {
                    "author": (n.get("author") or {}).get("username", "?"),
                    "body": (n.get("body") or "").strip(),
                }
                for n in notes[1:]
            ],
        })
    threads.sort(key=lambda t: t["resolved"])
    return threads


def transcript(threads):
    lines = ["# Reviewer comments already on this MR", ""]
    for thread in threads:
        state = "resolved" if thread["resolved"] else "open"
        where = thread["where"] or "general"
        lines.append(f"## [{state}] {where} — @{thread['author']}")
        lines.append("")
        lines.append(thread["body"])
        for reply in thread["replies"]:
            lines.append("")
            lines.append(f"**@{reply['author']}:**")
            lines.append("")
            lines.append(reply["body"])
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--iid", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max", type=int, default=40)
    args = parser.parse_args()

    threads = digest(fetch_discussions(args.project, args.iid))
    if not threads:
        return

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(transcript(threads))

    for thread in threads[: args.max]:
        state = "[resolved] " if thread["resolved"] else ""
        where = thread["where"] or "general"
        body = one_line(thread["body"])
        if len(body) > BODY_CHARS:
            body = body[: BODY_CHARS - 1] + "…"
        replies = f" (+{len(thread['replies'])} replies)" if thread["replies"] else ""
        print(f"COMMENT={state}{where} @{thread['author']}: {body}{replies}")
    print(f"COMMENTS_FILE={out}")
    if len(threads) > args.max:
        print(f"COMMENTS_MORE={len(threads) - args.max}")


if __name__ == "__main__":
    main()
