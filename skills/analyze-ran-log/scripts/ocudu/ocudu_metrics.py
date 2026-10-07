#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
ocudu_metrics.py — Query the METRICS lines of an OCUDU log.

Parses the [METRICS] lines with the `parsers` package of this repo (values normalized to us, bps and plain numbers),
and prints, for a layer, statistics of its fields or its rows, filtered by context fields and time.

Usage:
  python3 ocudu_metrics.py <path>                                   # layers, row counts, time spans and fields
  python3 ocudu_metrics.py <path> --layer sched_ue                  # count/min/mean/max of every numeric field
  python3 ocudu_metrics.py <path> --layer sched_ue --fields dl_brate,dl_mcs --by ue
  python3 ocudu_metrics.py <path> --layer sched_ue --where rnti=0x4601 --rows --fields dl_brate,ul_brate
  python3 ocudu_metrics.py <path> --layer mac --after 18:18:30 --before 18:18:40

<path>: a log file or a directory, resolved like ocudu_log_summary.py.

Options:
  --layer <L>         Metrics layer, e.g. sched_ue, sched, mac, rlc, exec. Without it, lists the layers.
  --fields <a,b,...>  Fields to show (default: all numeric fields for stats, all fields for rows).
  --where <k=v>       Keep rows whose field k equals v (numbers compare numerically, 0x values as text). Repeatable.
  --after/--before    Time window, as an ISO timestamp or a HH:MM:SS[.ffffff] time of day.
  --by <field>        Statistics per value of a context field, e.g. ue, rnti, pci.
  --rows              Print the rows (line number, time and fields) instead of statistics.
  --max-rows <N>      Rows printed at most (default: 200).
  -j <K>              Worker processes (default: one per CPU up to 8 for logs over 64 MB, else 1).
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "_lib"))

from ocudu_log_summary import primary_log_in, resolve_run_dir  # noqa: E402
from parsers.log import metrics  # noqa: E402

# Logs from this size are parsed in parallel by default.
PARALLEL_MIN_SIZE = 64 << 20
MAX_DEFAULT_WORKERS = 8


def resolve_log(path_str: str) -> Path:
    p = Path(path_str)
    if p.is_file():
        return p
    run_dir = resolve_run_dir(path_str)
    log = primary_log_in(run_dir)
    if log is None:
        raise FileNotFoundError(f"No OCUDU app log under {p}")
    return log


def parse_value(text: str):
    """A --where value as a number when it is one, else as text."""
    if text.lower().startswith("0x"):
        return text.lower()
    for convert in (int, float):
        try:
            return convert(text)
        except ValueError:
            pass
    return text


def matches_where(value, wanted) -> bool:
    """Whether a field value equals a --where value: as text, case-insensitively, for text values."""
    if isinstance(wanted, str):
        return str(value).lower() == wanted.lower()
    return value == wanted


def matches_time(ts, ref: str, after: bool) -> bool:
    if "T" in ref:
        value, bound = ts.isoformat(timespec="microseconds"), ref
    else:
        value, bound = ts.strftime("%H:%M:%S.%f")[: len(ref)], ref
    return value >= bound if after else value <= bound


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def stats_line(name: str, values: list, unit: str | None) -> str:
    nums = [v for v in values if is_number(v)]
    if not nums:
        return f"  {name:32s} {'':>8} (no numeric values)"
    unit_s = f" {unit}" if unit else ""
    return (
        f"  {name:32s} n={len(nums):<7d} min={fmt(min(nums))} mean={fmt(sum(nums) / len(nums))} "
        f"max={fmt(max(nums))}{unit_s}"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Query the METRICS lines of an OCUDU log")
    ap.add_argument("path")
    ap.add_argument("--layer")
    ap.add_argument("--fields")
    ap.add_argument("--where", action="append", default=[])
    ap.add_argument("--after")
    ap.add_argument("--before")
    ap.add_argument("--by")
    ap.add_argument("--rows", action="store_true")
    ap.add_argument("--max-rows", type=int, default=200)
    ap.add_argument("-j", type=int)
    args = ap.parse_args(argv)

    try:
        log = resolve_log(args.path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    layers = [args.layer] if args.layer else None
    if args.layer and args.layer not in metrics.LAYER_PATTERNS:
        print(f"Error: unknown layer {args.layer!r}. Known: {', '.join(metrics.LAYER_PATTERNS)}", file=sys.stderr)
        return 1
    where = []
    for w in args.where:
        key, sep, value = w.partition("=")
        if not sep:
            print(f"Error: --where needs k=v, got {w!r}", file=sys.stderr)
            return 1
        where.append((key, parse_value(value)))

    workers = args.j
    if workers is None:
        workers = min(MAX_DEFAULT_WORKERS, os.cpu_count() or 1) if log.stat().st_size >= PARALLEL_MIN_SIZE else 1
    parser = metrics.MetricsParser(layers)
    rows = []
    executor = None
    if workers > 1:
        executor = ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("forkserver"))
    try:
        for line_no, rec in parser.parse_file(log, executor):
            if args.after and not matches_time(rec["timestamp"], args.after, True):
                continue
            if args.before and not matches_time(rec["timestamp"], args.before, False):
                continue
            if not all(matches_where(rec.get(k), v) for k, v in where):
                continue
            rows.append((line_no, rec))
    finally:
        if executor:
            executor.shutdown()

    print(f"Log: {log}")
    if not args.layer:
        by_layer = defaultdict(list)
        for line_no, rec in rows:
            by_layer[rec["layer"]].append(rec)
        for layer, recs in sorted(by_layer.items()):
            fields = sorted({k for r in recs for k in r} - {"timestamp", "layer"})
            print(f"\n{layer}: {len(recs)} rows, {recs[0]['timestamp']:%H:%M:%S} .. {recs[-1]['timestamp']:%H:%M:%S}")
            units = parser.units[layer]
            print("  fields: " + ", ".join(f + (f" [{units[f]}]" if f in units else "") for f in fields))
        if not by_layer:
            print("No METRICS rows.")
        return 0

    units = parser.units[args.layer]
    recs = [r for _, r in rows]
    span = f" ({recs[0]['timestamp']:%H:%M:%S.%f} .. {recs[-1]['timestamp']:%H:%M:%S.%f})" if recs else ""
    print(f"Layer {args.layer}: {len(recs)} rows{span}")
    if not recs:
        return 0
    if args.fields:
        fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    elif args.rows:
        fields = list(dict.fromkeys(k for r in recs for k in r if k not in ("timestamp", "layer")))
    else:
        fields = sorted({k for r in recs for k, v in r.items() if is_number(v)})

    if args.rows:
        header = ["line", "time", *fields]
        print("  " + "  ".join(header))
        for line_no, rec in rows[: args.max_rows]:
            values = [fmt(rec.get(f)) for f in fields]
            print("  " + "  ".join([str(line_no), f"{rec['timestamp']:%H:%M:%S.%f}", *values]))
        if len(rows) > args.max_rows:
            more = len(rows) - args.max_rows
            print(f"  ... {more} more rows. Narrow with --where/--after/--before or raise --max-rows.")
        return 0

    groups = defaultdict(list)
    for rec in recs:
        groups[rec.get(args.by) if args.by else None].append(rec)
    for key, group in sorted(groups.items(), key=lambda kv: (kv[0] is None, str(kv[0]))):
        if args.by:
            print(f"\n{args.by}={key}: {len(group)} rows")
        for f in fields:
            print(stats_line(f, [r.get(f) for r in group], units.get(f)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
