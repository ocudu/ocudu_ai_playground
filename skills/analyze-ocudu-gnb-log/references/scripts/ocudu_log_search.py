#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
ocudu_log_search.py — Search an OCUDU gNB log with filtering.

Handles multi-line log blocks (RRC ASN.1 bodies, SIB1 dumps) correctly —
a filter that matches anywhere in a block (header + body) will return the
entire block.

Skips the CONFIG echo at the top of the file by default (everything before
the first timestamped line).

Usage:
  python3 ocudu_log_search.py <path> [options]

<path>: gnb.log file or any directory (resolved the same way as
ocudu_log_summary.py).

Options:
  --layer <LAYER>       Filter by log layer (e.g. RRC, NGAP, CU-CP, CU-CP-F1,
                        CU-CP-E1, CU-UP-E1, DU-F1, MAC, SCHED, PHY, PDCP, GTPU,
                        DU-MNG, METRICS, GNB, CONFIG, ALL). Case-insensitive,
                        matches the bracketed layer tag exactly (stripped of
                        padding spaces).
  --level <REGEX>       Filter by level (D, I, W, E, C). Multiple via regex,
                        e.g. "E|C|W".
  --ue <N>              Filter by `ue=N` token in the message.
  --rnti <HEX>          Filter by `c-rnti=0x<HEX>` token. Provide hex without
                        "0x" (e.g. 4601).
  --pci <N>             Filter by `pci=N` token.
  --after <ts>          Only include lines at or after the timestamp. Accepts
                        either a full ISO-8601 timestamp or a `HH:MM:SS.mmm`
                        partial — the partial form is matched against the time
                        portion only.
  --before <ts>         Symmetric to --after.
  --pattern <regex>     Additional regex pattern (searched across the entire
                        block, case-insensitive, multiline).
  --count               Print match count only (no block content).
  --max-lines <N>       Max output lines before truncation (default: 200).
  --include-config-echo Include the CONFIG echo at the top of the file (off by
                        default — it's the user's `ocudu_gnb.yml` plus
                        defaults, and adds no signal beyond the YAML).

Examples:
  # All RRC messages
  python3 ocudu_log_search.py gnb.log --layer RRC

  # NGAP procedures for ue=0
  python3 ocudu_log_search.py gnb.log --layer NGAP --ue 0

  # Count handovers
  python3 ocudu_log_search.py gnb.log --pattern "reconfigurationWithSync \\{" --count

  # PHY CRC failures in a window (partial timestamp form OK)
  python3 ocudu_log_search.py gnb.log --layer PHY --pattern "crc=KO" \\
      --after 18:18:30.000 --before 18:18:31.000

  # Errors and warnings across the run
  python3 ocudu_log_search.py gnb.log --level "E|C|W"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# Real event lines start with an ISO-8601 timestamp.
HEADER_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T(?P<time>\d{2}:\d{2}:\d{2}\.\d{6}))\s+"
    r"\[(?P<layer>[A-Z][A-Z0-9_ -]*?)\s*\]\s+"
    r"\[(?P<lvl>[A-Z])\]\s+"
)


def resolve_gnb_log(path_str: str) -> Path:
    p = Path(path_str).resolve()
    if p.is_file() and p.name == "gnb.log":
        return p
    if p.is_file():
        return p
    if (p / "gnb.log").exists():
        return p / "gnb.log"
    candidates = sorted(p.rglob("gnb.log"), key=lambda f: str(f))
    if candidates:
        return candidates[-1]
    raise FileNotFoundError(f"No gnb.log found at or under {p}")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Search OCUDU gNB log with filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("path", help="gnb.log file or containing directory")
    ap.add_argument("--layer", help="Layer filter (e.g. RRC, NGAP, CU-CP)")
    ap.add_argument("--level", help="Log-level regex (D|I|W|E|C)")
    ap.add_argument("--ue", help="Match `ue=N` in the message")
    ap.add_argument("--rnti", help="Match `c-rnti=0x<HEX>` (hex without 0x)")
    ap.add_argument("--pci", help="Match `pci=N` in the message")
    ap.add_argument("--after", help="Start timestamp (ISO or HH:MM:SS.mmm)")
    ap.add_argument("--before", help="End timestamp (ISO or HH:MM:SS.mmm)")
    ap.add_argument("--pattern", help="Regex pattern (full block, multiline, IGNORECASE)")
    ap.add_argument("--count", action="store_true", help="Print count only")
    ap.add_argument("--max-lines", type=int, default=200,
                    help="Max output lines before truncation (default: 200)")
    ap.add_argument("--include-config-echo", action="store_true",
                    help="Include the CONFIG echo at the top of the file")
    return ap.parse_args(argv)


def ts_matches_after(line_ts: str, line_time: str, ref: str) -> bool:
    """Return True if line is on/after ref. ref may be ISO or HH:MM:SS.mmm."""
    if "T" in ref:
        return line_ts >= ref
    # Allow lower-precision HH:MM:SS or HH:MM:SS.mmm — compare prefix-wise.
    return line_time[: len(ref)] >= ref


def ts_matches_before(line_ts: str, line_time: str, ref: str) -> bool:
    if "T" in ref:
        return line_ts <= ref
    return line_time[: len(ref)] <= ref


def block_matches(header_line: str, body_lines: list[str], args) -> bool:
    m = HEADER_RE.match(header_line)
    if not m:
        return False
    ts = m.group("ts")
    time_only = m.group("time")
    layer = m.group("layer").strip()
    lvl = m.group("lvl")

    if args.after and not ts_matches_after(ts, time_only, args.after):
        return False
    if args.before and not ts_matches_before(ts, time_only, args.before):
        return False

    if args.layer and layer.upper() != args.layer.upper():
        return False

    if args.level and not re.fullmatch(args.level, lvl):
        return False

    full_text = header_line
    if body_lines:
        full_text += "\n" + "\n".join(body_lines)

    if args.ue is not None:
        if not re.search(rf"\bue={re.escape(args.ue)}\b", full_text):
            return False

    if args.rnti is not None:
        # MAC/SCHED use `rnti=0x..` and `tc-rnti=0x..`; RRC/CU-CP use `c-rnti=0x..`.
        if not re.search(rf"(?:c-|tc-)?rnti=0x{re.escape(args.rnti)}\b",
                         full_text, re.IGNORECASE):
            return False

    if args.pci is not None:
        if not re.search(rf"\bpci={re.escape(args.pci)}\b", full_text):
            return False

    if args.pattern:
        if not re.search(args.pattern, full_text, re.IGNORECASE | re.MULTILINE):
            return False

    return True


def _is_config_echo_header(line: str) -> bool:
    """The `[CONFIG  ] [D] Input configuration (all values):` line, whose body is
    the ~440-line effective-config dump echoed at the top of every gnb.log."""
    m = HEADER_RE.match(line)
    return bool(m) and m.group("layer").strip() == "CONFIG" and \
        m.group("lvl") == "D" and "Input configuration" in line


def iter_blocks(log_path: Path, include_config_echo: bool):
    """Yield (header_line, body_lines) blocks from the log.

    A block is a header line (matching HEADER_RE) plus any subsequent
    non-header lines that belong to the same record (continuation lines
    for ASN.1 PDU dumps, SIB1 JSON, the CONFIG echo, ...).

    By default the giant CONFIG echo block (header + its untimestamped YAML body)
    is skipped entirely — it is redundant with ocudu_gnb.yml and would otherwise
    let `--pattern` match config text. Pass include_config_echo=True to keep it.
    """
    current_header = None
    current_body: list[str] = []
    skipping = False

    with open(log_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line:
                continue

            if HEADER_RE.match(line):
                if current_header is not None:
                    yield current_header, current_body
                if (not include_config_echo) and _is_config_echo_header(line):
                    current_header = None
                    current_body = []
                    skipping = True
                else:
                    current_header = line
                    current_body = []
                    skipping = False
            else:
                if skipping or current_header is None:
                    continue
                current_body.append(line)

        if current_header is not None:
            yield current_header, current_body


def search(args):
    log_path = resolve_gnb_log(args.path)

    matches: list[str] = []
    for header, body in iter_blocks(log_path, args.include_config_echo):
        if block_matches(header, body, args):
            block_text = header
            if body:
                block_text += "\n" + "\n".join(body)
            matches.append(block_text)

    if args.count:
        print(len(matches))
        return

    output_lines = 0
    shown = 0
    for block in matches:
        n_lines = block.count("\n") + 2
        if shown > 0 and output_lines + n_lines > args.max_lines:
            break
        print(block)
        print()
        output_lines += n_lines
        shown += 1

    if shown < len(matches):
        remaining = len(matches) - shown
        print(f"... {remaining} more matching block(s) not shown (stopped near the "
              f"{args.max_lines}-line cap). Narrow with --after/--before/--ue/--rnti/--pci.")


if __name__ == "__main__":
    args = parse_args()
    try:
        search(args)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
