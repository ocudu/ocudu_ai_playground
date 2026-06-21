#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
viavi_log_search.py - Search a VIAVI command log with filtering.

Block-aware: a block is one timestamped line plus the continuation lines that
follow it (e.g. an RRC event's "Cell Info:" body, or a UE's GETSTATS stat rows).
A filter that matches anywhere in a block returns the whole block.

Usage:
  python3 viavi_log_search.py <path> [options]

<path>: a *_Command_Log*.txt/.zip file or a directory (resolved like
viavi_log_summary.py — newest log, .txt preferred, .zip read in place).

Options:
  --ue <id>           Filter to blocks mentioning "UE Id:<id>" / "UE ID: <id>"
  --event <substr>    Filter to "I: CMPI" event lines containing <substr>
                      (e.g. "Random Access Error", "REGISTRATION IND")
  --after <ts>        Only blocks at or after HH:MM:SS:mmm
  --before <ts>       Only blocks at or before HH:MM:SS:mmm
  --pattern <regex>   Additional regex, searched across the whole block
  --count             Print the match count only
  --max-lines <N>     Max output lines before truncation (default: 200)

Examples:
  # Every random-access error
  python3 viavi_log_search.py <log> --event "Random Access Error"

  # Everything about UE 113 in a time window
  python3 viavi_log_search.py <log> --ue 113 --after 11:19:00:000 --before 11:21:00:000

  # Count NR registration indications
  python3 viavi_log_search.py <log> --event "REGISTRATION IND" --count
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import viavi_log_summary  # reuse resolve_log() / open_log() / TS_RE

TS_RE = viavi_log_summary.TS_RE


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Search a VIAVI command log with filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("path", help="command log (.txt/.zip) or containing directory")
    ap.add_argument("--ue", help="UE id filter (e.g. 113)")
    ap.add_argument("--event", help='"I: CMPI" event substring filter')
    ap.add_argument("--after", help="start timestamp HH:MM:SS:mmm (inclusive)")
    ap.add_argument("--before", help="end timestamp HH:MM:SS:mmm (inclusive)")
    ap.add_argument("--pattern", help="regex searched across the full block")
    ap.add_argument("--count", action="store_true", help="print match count only")
    ap.add_argument("--max-lines", type=int, default=200,
                    help="max output lines before truncation (default: 200)")
    return ap.parse_args(argv)


def block_matches(header: str, body: list[str], args, ue_re) -> bool:
    m = TS_RE.match(header)
    if not m:
        return False
    ts, payload = m.group(2), m.group(3)

    if args.after and ts < args.after:
        return False
    if args.before and ts > args.before:
        return False

    if args.event:
        if not payload.startswith("I: CMPI") or args.event.lower() not in payload.lower():
            return False

    full = "\n".join([header, *body])

    if ue_re and not ue_re.search(full):
        return False
    if args.pattern and not re.search(args.pattern, full, re.IGNORECASE | re.MULTILINE):
        return False
    return True


def search(args) -> None:
    log_path = viavi_log_summary.resolve_log(args.path)
    # Match "UE Id:113" and "UE ID: 113" with an exact-id boundary.
    ue_re = re.compile(rf"UE I[dD]:\s*{re.escape(args.ue)}\b") if args.ue else None

    blocks: list[str] = []
    header = None
    body: list[str] = []

    def flush():
        nonlocal header, body
        if header is not None and block_matches(header, body, args, ue_re):
            blocks.append("\n".join([header, *body]))
        header, body = None, []

    with viavi_log_summary.open_log(log_path) as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            if TS_RE.match(line):
                flush()
                header, body = line, []
            elif header is not None:
                body.append(line)
        flush()

    if args.count:
        print(len(blocks))
        return

    shown = out_lines = 0
    for b in blocks:
        n = b.count("\n") + 2
        if shown > 0 and out_lines + n > args.max_lines:
            break
        print(b)
        print()
        out_lines += n
        shown += 1

    if shown < len(blocks):
        print(f"... {len(blocks) - shown} more matching block(s) not shown (stopped near "
              f"the {args.max_lines}-line cap). Narrow with --after/--before/--ue/--event.")


if __name__ == "__main__":
    args = parse_args()
    try:
        search(args)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
