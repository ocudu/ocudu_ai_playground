#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Procedure-code counter for NGAP / F1AP / E1AP.

Usage:
    extract_proc_codes.py <pcap> --proto ngap
    extract_proc_codes.py <pcap> --proto f1ap --time-range <start-epoch>,<end-epoch>
    extract_proc_codes.py <pcap> --proto ngap --initiating-only
    extract_proc_codes.py <pcap> --proto e1ap --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import utils
from parsers.pcap import overview
from parsers.pcap.names import proc_name


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcap", help="path to a single-protocol pcap")
    ap.add_argument("--proto", required=True, choices=["ngap", "f1ap", "e1ap"])
    ap.add_argument("--initiating-only", action="store_true",
                    help="only count initiatingMessage frames (not Response/Failure)")
    ap.add_argument("--time-range", help="epoch range A,B  inclusive on A, exclusive on B")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    pcap = Path(args.pcap)
    if not pcap.is_file():
        print(f"error: not a file: {pcap}", file=sys.stderr)
        return 1
    time_range = None
    if args.time_range:
        try:
            a, b = (float(x) for x in args.time_range.split(","))
        except ValueError:
            print(f"error: bad --time-range: {args.time_range}", file=sys.stderr)
            return 1
        time_range = (a, b)
    try:
        counts = overview.proc_code_counts(
            utils.TSHARK, pcap, args.proto, initiating_only=args.initiating_only, time_range=time_range
        )
    except utils.TsharkError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    proto = args.proto
    if args.json:
        print(json.dumps({"proto": proto, "total": sum(counts.values()), "counts": counts.most_common()}, indent=2))
        return 0

    print(f"== {proto} procedure codes  (total={sum(counts.values())})")
    if not counts:
        print("  (no matching rows)")
        return 0
    for code, count in counts.most_common():
        print(f"  {proc_name(proto, code):<32} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
