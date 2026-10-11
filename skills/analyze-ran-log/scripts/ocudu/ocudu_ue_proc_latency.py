#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Per-stage latency profiler for OCUDU DU UE-lifecycle procedures.

Measures DU-MNG / MAC / SCHED / DU-F1 procedure stages for UE creation,
(re)configuration and removal, with parsers.log.procedures of this repo.
Stages that a build does not log are skipped (reports only present stages).

Usage: ocudu_ue_proc_latency.py <gnb.log|srsdu.log> [proc-filter-substr]
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "_lib"))

from parsers.log import procedures  # noqa: E402


def fmt(us: float) -> str:
    return f"{us / 1000:.2f}ms" if us >= 1000 else f"{us:.0f}us"


def report(proc: str, insts: list[procedures.Instance]) -> None:
    print(f'\n### proc="{proc}"   instances={len(insts)}')
    hdr = f"{'stage transition':34} {'n':>5} {'mean':>9} {'p50':>9} {'p90':>9} {'p99':>9} {'max':>10}"
    print(hdr)
    print("-" * len(hdr))
    for label, frm, to in procedures.transitions(proc):
        st = procedures.stats(procedures.latencies(insts, frm, to))
        if st is None:
            print(f"{label:34} {0:>5}       -")
            continue
        print(f"{label:34} {st.n:>5} {fmt(st.mean):>9} {fmt(st.p50):>9} {fmt(st.p90):>9} {fmt(st.p99):>9} "
              f"{fmt(st.max):>10}")


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit("usage: ocudu_ue_proc_latency.py <gnb.log|srsdu.log> [proc-filter-substr]")
    path = sys.argv[1]
    filt = sys.argv[2] if len(sys.argv) > 2 else None
    with open(path, errors="replace") as f:
        found = procedures.instances(f)
    print(f"# log: {path}")
    for group, procs in procedures.GROUPS:
        procs = [p for p in procs if found[p] and (not filt or filt in p)]
        if not procs:
            continue
        print(f"\n========== {group} ==========")
        for p in procs:
            report(p, found[p])
    return 0


if __name__ == "__main__":
    sys.exit(main())
