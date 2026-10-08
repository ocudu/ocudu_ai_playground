#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Unified epoch-sorted timeline across all 5 pcaps in a run directory.

Usage:
    correlate_run.py <run-dir>
    correlate_run.py <run-dir> --around <epoch> --window-ms 2000
    correlate_run.py <run-dir> --ue 42
    correlate_run.py <run-dir> --protocols ngap,f1ap
    correlate_run.py <run-dir> --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import utils
from parsers.pcap import timeline
from parsers.pcap.run import PCAP_NAMES, is_run_dir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", help="OCUDU run directory containing the 5 sibling pcaps")
    ap.add_argument("--around", type=float, help="centre epoch for the window")
    ap.add_argument("--window-ms", type=int, default=2000,
                    help="full window width in ms (centred on --around). Default 2000.")
    ap.add_argument("--ue", help="filter to events mentioning this identifier")
    ap.add_argument("--protocols", default="ngap,f1ap,e1ap,mac,rlc",
                    help="comma-separated subset to include")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not is_run_dir(run_dir):
        print(f"error: not a run directory (need ≥2 of {PCAP_NAMES}): {run_dir}", file=sys.stderr)
        return 1

    protocols = [p.strip() for p in args.protocols.split(",") if p.strip()]
    events = timeline.run_events(
        utils.TSHARK, run_dir, protocols, around=args.around, window_ms=args.window_ms, ue=args.ue
    )

    if args.json:
        print(json.dumps(events, indent=2))
        return 0

    if not events:
        print("(no events in window)")
        return 0
    for e in events:
        ue_str = ",".join(e["ue_ids"]) if e["ue_ids"] else "-"
        print(f"{e['iso']}  {e['file']:<4}  frame={e['frame']:>6}  "
              f"ue={ue_str:<12}  {e['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
