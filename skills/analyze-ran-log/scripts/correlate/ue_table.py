#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
ue_table.py — The UEs of an OCUDU run, one row each with all their identifiers.

Combines the UE contexts of the F1AP pcap and of the OCUDU log of a run with the `parsers` package of this repo
(parsers.correlate): an F1AP UE context (du_f1ap, cu_f1ap, C-RNTI) joins the log UE context (DU UE index `ue`, RNTI)
of the same RNTI with overlapping lifetimes, or, for a log UE without RNTI, the one created nearest in time. Each row
is one UE context: a handover or reestablishment gives a new row, with a new RNTI and new F1AP ids.

Usage:
  python3 ue_table.py <path>                          # all UEs of the run
  python3 ue_table.py <path> --where rnti=0x4602      # the UE of an RNTI
  python3 ue_table.py <path> --where ue=1             # the UEs that had DU UE index 1 (reused over time)
  python3 ue_table.py <path> --after 12:24:34 --before 12:24:40 --csv

<path>: a run dir, component dir or test dir, resolved like ocudu_log_summary.py, or the log itself.

Options:
  --where <k=v>       Keep UEs with identifier k equal to v: rnti, ue, du_f1ap, cu_f1ap. Repeatable.
  --after/--before    Keep UEs alive in a window, as an ISO timestamp or a HH:MM:SS[.ffffff] time of day (UTC).
  --with-ra           Also list the random accesses of no UE (a PRACH in the log only, e.g. a failed RA).
  --log <file>        Log to use instead of the one of the run.
  --f1ap <file>       F1AP pcap to use instead of the one of the run. Without one, the UEs are the log ones only.
  --csv               Print CSV.

The DU UE index `ue` is reused soon after a UE is released; RNTIs and F1AP ids are not, so prefer them as keys.
Joining NGAP and E1AP contexts is not supported.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "_lib"))
sys.path.insert(0, str(SCRIPT_DIR.parent / "ocudu"))

from ocudu_log_summary import primary_log_in, resolve_run_dir  # noqa: E402
from parsers.correlate import run  # noqa: E402
from parsers.correlate.ues import Ue  # noqa: E402
from parsers.pcap.tshark import Tshark  # noqa: E402
from parsers.ran.rnti import normalize as normalize_rnti  # noqa: E402

COLUMNS = ("start", "end", "duration_s", "rnti", "ue", "du_f1ap", "cu_f1ap", "sources")


def utc(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def time_bound(ref: str, epoch: float) -> str:
    """The form of a timestamp that compares with a --after/--before value."""
    t = utc(epoch)
    if "T" in ref:
        return t.replace(tzinfo=None).isoformat(timespec="microseconds")
    return t.strftime("%H:%M:%S.%f")[: len(ref)]


def matches(ue: Ue, where: list[tuple[str, str]]) -> bool:
    for name, value in where:
        if name == "rnti":
            value = normalize_rnti(value) or value
        if value not in ue.ids.get(name, ()):
            return False
    return True


def row(ue: Ue, names: dict[str, str]) -> dict[str, str]:
    """A table row of a UE, with the kinds of its sources, given the kind of each source by name."""
    sources = {source for source, _ in ue.parts}
    kinds = [kind for name, kind in names.items() if name in sources]
    return {
        "start": utc(ue.t_start).strftime("%H:%M:%S.%f")[:-3],
        "end": "open" if ue.open else utc(ue.t_end).strftime("%H:%M:%S.%f")[:-3],
        "duration_s": f"{ue.t_end - ue.t_start:.3f}",
        **{name: ",".join(ue.ids.get(name, [])) or "-" for name in ("rnti", "ue", "du_f1ap", "cu_f1ap")},
        "sources": "+".join(kinds),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--where", action="append", default=[], metavar="K=V")
    ap.add_argument("--after")
    ap.add_argument("--before")
    ap.add_argument("--with-ra", action="store_true")
    ap.add_argument("--log")
    ap.add_argument("--f1ap")
    ap.add_argument("--csv", action="store_true")
    args = ap.parse_args(argv)

    where = []
    for item in args.where:
        name, sep, value = item.partition("=")
        if not sep:
            ap.error(f"--where takes k=v, not {item!r}")
        where.append((name.strip(), value.strip()))

    path = Path(args.path)
    run_dir = path.parent if path.is_file() else resolve_run_dir(args.path)
    log = Path(args.log) if args.log else (path if path.is_file() else primary_log_in(run_dir))
    f1ap = Path(args.f1ap) if args.f1ap else run_dir / "f1ap.pcap"
    if not f1ap.is_file():
        print(f"note: no F1AP pcap at {f1ap}; the UEs are the ones of the log only.", file=sys.stderr)
        f1ap = None
    if log is None or not log.is_file():
        print(f"error: no OCUDU log under {run_dir}", file=sys.stderr)
        return 1

    ues = run.run_ues(Tshark(), f1ap, [log])
    # A log UE without DU UE index and F1AP context is a random access of no UE, e.g. a failed RA.
    ra_only = [ue for ue in ues if "ue" not in ue.ids and "du_f1ap" not in ue.ids]
    shown = [
        ue for ue in ues
        if (args.with_ra or ue not in ra_only)
        and matches(ue, where)
        and (not args.after or time_bound(args.after, ue.t_end) >= args.after or ue.open)
        and (not args.before or time_bound(args.before, ue.t_start) <= args.before)
    ]
    names = {**({f1ap.name: "f1ap"} if f1ap else {}), log.name: "log"}
    rows = [row(ue, names) for ue in shown]

    if args.csv:
        writer = csv.DictWriter(sys.stdout, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        return 0

    print(f"run: {run_dir}")
    print(f"sources: {f1ap.name if f1ap else '(no f1ap.pcap)'}, {log.name}")
    joined = sum(1 for ue in ues if "du_f1ap" in ue.ids and "ue" in ue.ids)
    print(f"UEs: {len(ues) - len(ra_only)} ({joined} in both the pcap and the log), random accesses of no UE: {len(ra_only)}"
          + ("" if args.with_ra else " (hidden, see --with-ra)"))
    if not rows:
        print("no UE matches.")
        return 0
    widths = {c: max(len(c), *(len(r[c]) for r in rows)) for c in COLUMNS}
    print("  ".join(c.ljust(widths[c]) for c in COLUMNS))
    for r in rows:
        print("  ".join(r[c].ljust(widths[c]) for c in COLUMNS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
