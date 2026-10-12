#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
schedtrace_collisions.py — Find colliding allocations in OCUDU scheduler event traces.

Decodes schedtrace_cell<N>.bin with the `parsers` package of this repo and prints the pairs of allocations of a slot
whose resources overlap: PDSCH with PDSCH (UE, SIB, RAR, paging), PUSCH with PUSCH, PUSCH with PUCCH, and PDCCH with
PDCCH (CCEs shared in a CORESET).

The VRBs of PDSCHs of DCI format 1_0 in a common search space (SIB, RAR, paging, fallback) count from their CORESET,
the others from their BWP. PDCCHs are not checked against PDSCHs.

Usage:
  python3 schedtrace_collisions.py <path>                            # every collision, then counts per kind
  python3 schedtrace_collisions.py <path> --kinds PUSCH-PUCCH --rnti 0x4601
  python3 schedtrace_collisions.py <path> --summary

<path>: a schedtrace_cell<N>.bin, or a directory, whose schedtrace_cell*.bin are all searched.

Options:
  --kinds <a,b,...>   Kinds to report: PDSCH-PDSCH, PUSCH-PUSCH, PUSCH-PUCCH, PDCCH-PDCCH (default: all).
  --rnti <R>          Keep collisions with an allocation of this RNTI, hex (0x4601) or decimal. Repeatable.
  --summary           Print only the counts per kind, with the first and last slot of each.
  --max-rows <N>      Collisions printed at most per trace (default: 200).
  -j <K>              Worker processes (default: one per CPU up to 8 for traces over 16 MB, else 1).
"""

from __future__ import annotations

import argparse
import mmap
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "_lib"))

from parsers import schedtrace  # noqa: E402
from parsers.schedtrace import collisions, grid  # noqa: E402

# Traces from this size are searched in parallel by default.
PARALLEL_MIN_SIZE = 16 << 20
MAX_DEFAULT_WORKERS = 8
CHUNKS_PER_WORKER = 4


def traces_in(path_str: str) -> list[Path]:
    p = Path(path_str)
    if p.is_file():
        return [p]
    if p.is_dir():
        found = sorted(p.rglob("schedtrace_cell*.bin"))
        if found:
            return found
    raise FileNotFoundError(f"No schedtrace_cell*.bin at {p}")


def find_chunk(path: str, start: int, end: int) -> list[collisions.Collision]:
    return list(collisions.find(path, start, end))


def find_all(path: Path, workers: int) -> list[collisions.Collision]:
    if workers <= 1:
        return list(collisions.find(path))
    with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        offsets = schedtrace.offsets(mm)
    if not offsets:
        return []
    step = max(1, -(-len(offsets) // (workers * CHUNKS_PER_WORKER)))
    bounds = [*offsets[::step], path.stat().st_size]
    args = [(str(path), lo, hi) for lo, hi in zip(bounds, bounds[1:])]
    out: list[collisions.Collision] = []
    # Workers fork from a single-threaded script, so the default start method is safe and fastest.
    with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("fork")) as pool:
        for res in pool.map(find_chunk, *zip(*args)):
            out.extend(res)
    return out


def parse_rnti(text: str) -> int:
    return int(text, 16) if text.lower().startswith("0x") else int(text)


def rnti_text(rnti: int | None) -> str:
    return "-" if rnti is None else f"0x{rnti:04x}"


def describe(alloc: dict, kind: str) -> str:
    """One allocation of a collision: its decision item, RNTI and resources."""
    list_name, index = alloc["item"]
    head = f"{list_name}[{index}] rnti={rnti_text(alloc.get('rnti'))}"
    if kind == "PDCCH-PDCCH":
        return f"{head} coreset={alloc['coreset_id']} cces=[{alloc['cce']},{alloc['cce'] + alloc['nof_cces']})"
    rects = " ".join(f"syms=[{s},{s + ns}) crbs=[{c},{c + nc})" for s, ns, c, nc in alloc["rects"])
    return f"{head} {rects}"


def overlap_text(c: collisions.Collision) -> str:
    if c.kind == "PDCCH-PDCCH":
        return " ".join(f"cces=[{lo},{lo + n})" for lo, n in c.overlap)
    return " ".join(f"syms=[{s},{s + ns}) crbs=[{lo},{lo + n})" for s, ns, lo, n in c.overlap)


def time_text(timestamp_us: int) -> str:
    return datetime.fromtimestamp(timestamp_us / 1e6, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--kinds", default=",".join(collisions.KINDS))
    ap.add_argument("--rnti", action="append", type=parse_rnti, default=[])
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--max-rows", type=int, default=200)
    ap.add_argument("-j", type=int, default=None)
    args = ap.parse_args()

    kinds = {k.strip().upper() for k in args.kinds.split(",") if k.strip()}
    if unknown := kinds - set(collisions.KINDS):
        ap.error(f"unknown kinds {sorted(unknown)}, expected some of {', '.join(collisions.KINDS)}")
    rntis = set(args.rnti)

    status = 0
    for path in traces_in(args.path):
        workers = args.j
        if workers is None:
            workers = min(MAX_DEFAULT_WORKERS, os.cpu_count() or 1) if path.stat().st_size >= PARALLEL_MIN_SIZE else 1
        try:
            cell = grid.cell_of(next(schedtrace.read(path)))
        except schedtrace.FormatError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            status = 1
            continue
        slots_per_frame = round(0.01 / cell.slot_duration_s)
        found = [
            c for c in find_all(path, workers)
            if c.kind in kinds and (not rntis or c.a.get("rnti") in rntis or c.b.get("rnti") in rntis)
        ]
        print(f"== {path}: {len(found)} collisions")
        if not args.summary:
            for c in found[: args.max_rows]:
                sfn, slot = divmod(c.slot_tx, slots_per_frame)
                print(f"{time_text(c.timestamp_us)} slot={sfn % 1024}.{slot} {c.kind}: {describe(c.a, c.kind)}"
                      f" | {describe(c.b, c.kind)} | overlap {overlap_text(c)}")
            if len(found) > args.max_rows:
                print(f"... {len(found) - args.max_rows} more, see --max-rows")
        for kind in collisions.KINDS:
            of_kind = [c for c in found if c.kind == kind]
            if of_kind:
                print(f"{kind}: {len(of_kind)}, first {time_text(of_kind[0].timestamp_us)}, "
                      f"last {time_text(of_kind[-1].timestamp_us)}")
    return status


if __name__ == "__main__":
    sys.exit(main())
