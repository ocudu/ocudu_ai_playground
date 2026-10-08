#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Compact overview of an OCUDU pcap or run directory.

For each pcap: packet count, duration, first/last epoch, distinct UE IDs,
top procedure codes (or PDU types for MAC/RLC), and count of Failure/Reject
PDUs.

Usage:
    pcap_overview.py <path>              # path is a .pcap or a run directory
    pcap_overview.py <path> --top 5      # show top N procedure codes
    pcap_overview.py <path> --json       # machine-readable output

Exit codes:
    0  - success
    1  - unrecoverable error (file missing, tshark unavailable)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import utils
from parsers.pcap import overview
from parsers.pcap.names import proc_name
from parsers.pcap.run import PCAP_NAMES


def render_text(summaries: list[dict]) -> str:
    lines: list[str] = []
    for s in summaries:
        lines.append(f"== {s['file']} ({s['proto']})")
        if s.get("empty") or s["packets"] == 0:
            lines.append("  (no packets)")
            continue
        lines.append(f"  packets: {s['packets']}")
        lines.append(
            f"  range:   {s.get('first_iso','?')} .. {s.get('last_iso','?')} "
            f"({s.get('duration_s', 0):.3f} s)"
        )
        if "distinct_ues_by_label" in s:
            parts = []
            for label, vals in s["distinct_ues_by_label"].items():
                if not vals:
                    continue
                if len(vals) <= 5:
                    parts.append(f"{label}({len(vals)})={','.join(vals)}")
                else:
                    parts.append(f"{label}({len(vals)})={','.join(vals[:5])},…")
            if parts:
                lines.append(f"  ues:     {'  '.join(parts)}")
        if "top_procedures" in s and s["top_procedures"]:
            top = ", ".join(f"{proc_name(s['proto'], code)}×{count}" for code, count in s["top_procedures"])
            lines.append(f"  top:     {top}")
        if s.get("failures") is not None:
            lines.append(f"  failures: {s['failures']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help=".pcap file or a run directory")
    ap.add_argument("--top", type=int, default=5, help="top N procedure codes per pcap")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    p = Path(args.path)
    if not p.exists():
        print(f"error: not found: {p}", file=sys.stderr)
        return 1
    if p.is_dir():
        targets = [p / name for name in PCAP_NAMES if (p / name).is_file()]
        if not targets:
            print(f"error: no OCUDU pcaps in {p}", file=sys.stderr)
            return 1
    else:
        targets = [p]

    try:
        summaries = [overview.summarise(utils.TSHARK, t, top=args.top) for t in targets]
    except utils.TsharkError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(summaries, indent=2) if args.json else render_text(summaries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
