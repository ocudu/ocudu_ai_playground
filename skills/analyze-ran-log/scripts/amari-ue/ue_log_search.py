#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
ue_log_search.py - Search Amarisoft UE log with filtering.

Handles multi-line log blocks (RRC/NAS PDU bodies) correctly —
a filter that matches anywhere in a block (header + body) will
return the entire block.

Usage:
  python3 ue_log_search.py <path> [options]

<path>: ue.log file or any directory (resolved the same way as ue_log_summary.py)

Options:
  --layer <LAYER>       Filter by log layer: NAS, RRC, PHY, MAC, RLC, PDCP, PROD, TRX
  --ue <ue_id>          Filter by UE ID (4-char hex, e.g. 0001, 000a, 0080)
  --cell <cell_id>      Filter by cell index (2-char decimal, e.g. 00, 01)
  --after <ts>          Only include lines at or after HH:MM:SS.mmm
  --before <ts>         Only include lines at or before HH:MM:SS.mmm
  --pattern <regex>     Additional regex pattern (searched across entire block)
  --count               Print match count only (no block content)
  --max-lines <N>       Max output lines before truncation (default: 200)

Examples:
  # All NAS state transitions
  python3 ue_log_search.py ue.log --layer NAS --pattern "New state"

  # RRC messages for UE 0001 after a specific time
  python3 ue_log_search.py ue.log --layer RRC --ue 0001 --after 12:24:34.000

  # Count PRACH attempts
  python3 ue_log_search.py ue.log --layer PHY --pattern "PRACH:" --count

  # Handovers (match the ASN.1 body structure, not the bare word, which also
  # appears in diagnostic log lines)
  python3 ue_log_search.py ue.log --pattern "reconfigurationWithSync {" --count

  # PHY CRC failures in a time window
  python3 ue_log_search.py ue.log --layer PHY --pattern "crc=FAIL" \\
      --after 12:24:34.000 --before 12:24:35.000
"""

import re
import sys
import argparse
from pathlib import Path


LINE_RE = re.compile(r"^(\d{2}:\d{2}:\d{2}\.\d{3}) \[(\w+)\]")


def resolve_ue_log(path_str: str) -> Path:
    p = Path(path_str).resolve()
    if p.is_file() and p.name == "ue.log":
        return p
    if p.is_file():
        return p  # allow other file paths too
    if (p / "ue.log").exists():
        return p / "ue.log"
    candidates = sorted(p.rglob("ue.log"), key=lambda f: str(f))
    if candidates:
        return candidates[-1]
    raise FileNotFoundError(f"No ue.log found at or under {p}")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Search Amarisoft UE log with filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("path", help="ue.log file or containing directory")
    ap.add_argument("--layer", help="Layer filter (NAS, RRC, PHY, MAC, RLC, PDCP, PROD, TRX)")
    ap.add_argument("--ue", help="UE ID filter (4-char hex, e.g. 0001, 000a)")
    ap.add_argument("--cell", help="Cell ID filter (e.g. 00, 01)")
    ap.add_argument("--after", help="Start timestamp HH:MM:SS.mmm (inclusive)")
    ap.add_argument("--before", help="End timestamp HH:MM:SS.mmm (inclusive)")
    ap.add_argument("--pattern", help="Regex pattern (searched across full block)")
    ap.add_argument("--count", action="store_true", help="Print count only")
    ap.add_argument("--max-lines", type=int, default=200,
                    help="Max output lines before truncation (default: 200)")
    return ap.parse_args(argv)


def block_matches(header_line: str, body_lines: list[str], args) -> bool:
    ts_m = LINE_RE.match(header_line)
    if not ts_m:
        return False
    ts = ts_m.group(1)
    layer = ts_m.group(2)

    # Time range
    if args.after and ts < args.after:
        return False
    if args.before and ts > args.before:
        return False

    # Layer filter
    if args.layer and layer.upper() != args.layer.upper():
        return False

    # Assemble full text (header + body) for content searches
    full_text = header_line
    if body_lines:
        full_text += "\n" + "\n".join(body_lines)

    # Positional field match. Fields after the "[LAYER]" tag are:
    #   <dir> <ue_id> <cell_id> ...   (ue_id is the pseudo-id `f000` on broadcast
    #   RRC lines, a 4-char hex UE id otherwise).
    # Matching by position avoids false hits (e.g. substring "00" inside an RNTI).
    after = header_line.split("]", 1)[1].split() if "]" in header_line else []
    ue_field = after[1] if len(after) > 1 else None
    cell_field = after[2] if len(after) > 2 else None

    if args.ue and ue_field != args.ue:
        return False
    if args.cell and cell_field != args.cell:
        return False

    # Pattern filter (across entire block, multiline so ^ and $ work per line)
    if args.pattern:
        if not re.search(args.pattern, full_text, re.IGNORECASE | re.MULTILINE):
            return False

    return True


def search(args):
    log_path = resolve_ue_log(args.path)

    output_blocks = []

    current_header = None
    current_body = []

    def process_block():
        nonlocal current_header, current_body
        if current_header is None:
            return
        if block_matches(current_header, current_body, args):
            block_text = current_header
            if current_body:
                block_text += "\n" + "\n".join(current_body)
            output_blocks.append(block_text)
        current_header = None
        current_body = []

    with open(log_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line:
                continue
            if line.startswith("#"):
                continue

            if LINE_RE.match(line):
                process_block()
                current_header = line
                current_body = []
            else:
                if current_header is not None:
                    current_body.append(line)

        process_block()  # flush last block

    if args.count:
        print(len(output_blocks))
        return

    # Print whole blocks only; stop before exceeding the line cap (always show ≥1).
    output_lines = 0
    shown_blocks = 0
    for block in output_blocks:
        n_lines = block.count("\n") + 2  # block lines + blank separator
        if shown_blocks > 0 and output_lines + n_lines > args.max_lines:
            break
        print(block)
        print()
        output_lines += n_lines
        shown_blocks += 1

    if shown_blocks < len(output_blocks):
        remaining = len(output_blocks) - shown_blocks
        print(f"... {remaining} more matching block(s) not shown (stopped near the "
              f"{args.max_lines}-line cap). Narrow with --after/--before/--ue/--cell.")


if __name__ == "__main__":
    args = parse_args()
    try:
        search(args)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
