# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Ad-hoc metrics of an OCUDU log: the numeric values of a key=value field in its lines, e.g. tbs=5889 of the slot
decision lines of the scheduler, with the time of their log entry.

Lines may be kept to those matching a regular expression, and each value may take the value of a split key, the
nearest one before it in its line, e.g. the ue= of the grant a tbs= belongs to. Numbers with a unit are scaled to the
canonical unit of the METRICS lines, e.g. kbps to bps.
"""

from __future__ import annotations

import mmap
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .chunks import ENTRY_START_RE
from .metrics import normalize_number

# Characters of a key, as in key=value fields, e.g. c-rnti, cw[0] or dl_bo.
_KEY_CHARS = r"[\w.\-\[\]]"
# Timestamp at the start of an entry line.
_TIMESTAMP_RE = re.compile(rb"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
# Bytes looked back for the header of the entry of a continuation line.
_MAX_LOOKBACK = 1 << 20


@dataclass(frozen=True)
class Spec:
    """An ad-hoc metric: the values of key, in the lines that match filter, if any, split by the value of split_key."""

    key: str
    filter: str | None = None
    split_key: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(_KEY_CHARS + "+", self.key):
            raise ValueError(f"Invalid key {self.key!r}.")
        if self.split_key is not None and not re.fullmatch(_KEY_CHARS + "+", self.split_key):
            raise ValueError(f"Invalid split key {self.split_key!r}.")
        if self.filter:
            try:
                re.compile(self.filter)
            except re.error as e:
                raise ValueError(f"Invalid filter: {e}.") from None


def value_re(key: str) -> re.Pattern[bytes]:
    """Pattern of the numeric values of a key, with "num" and an optional "unit"."""
    return re.compile(
        rb"(?<![\w.\-\[\]])" + re.escape(key.encode())
        + rb"=(?P<num>[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?P<unit>[A-Za-z%]+)?(?![\w.])"
    )


def split_re(key: str) -> re.Pattern[bytes]:
    """Pattern of the values of a split key, up to a space or a separator."""
    return re.compile(rb"(?<![\w.\-\[\]])" + re.escape(key.encode()) + rb"=(?P<value>[^\s,;()\[\]]+)")


def scan(path: str, start: int, end: int, first_line: int, spec: Spec) -> dict:
    """Scans the byte range [start, end) of a log, whose first line is line first_line, for the values of a spec.

    Returns "rows" of (time in seconds since the epoch, line number, line offset, value, split value or None), in
    file order, and "unit", the unit of the values when they have one. Lines without a timestamp take the one of the
    entry they belong to.
    """
    values = value_re(spec.key)
    splits = split_re(spec.split_key) if spec.split_key else None
    keep = re.compile(spec.filter, re.IGNORECASE) if spec.filter else None
    rows: list[tuple] = []
    unit: str | None = None
    with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        line_no, counted_to = first_line, start
        line_start, line, t = -1, b"", None
        # Lines are only read where the key is found, and lines counted between them, which keeps the scan in C.
        for m in values.finditer(mm, start, end):
            pos = m.start()
            newline = mm.rfind(b"\n", start, pos)
            if (newline + 1 if newline != -1 else start) != line_start:
                line_start = newline + 1 if newline != -1 else start
                line_no += mm[counted_to:line_start].count(b"\n")
                counted_to = line_start
                line_end = mm.find(b"\n", pos, end)
                line = mm[line_start: end if line_end == -1 else line_end]
                t = None
                if keep is None or keep.search(line.decode("utf-8", "replace")):
                    t = _entry_time(mm, line_start, start)
            if t is None:
                continue
            value, value_unit, _ = normalize_number(m["num"].decode(), m["unit"].decode() if m["unit"] else None)
            if value_unit is not None:
                unit = unit or value_unit
            split = None
            if splits is not None:
                found = None
                for found in splits.finditer(line, 0, pos - line_start):
                    pass
                split = found["value"].decode("utf-8", "replace") if found else None
            rows.append((t, line_no, line_start, value, split))
    return {"rows": rows, "unit": unit}


def _entry_time(mm: mmap.mmap, line_start: int, floor: int) -> float | None:
    """The time of the entry of the line at line_start: its own timestamp, else that of the nearest line before it
    with one, looking back at most _MAX_LOOKBACK bytes and not before floor, the start of a range at an entry.
    """
    pos = line_start
    lowest = max(floor, line_start - _MAX_LOOKBACK)
    while True:
        if ENTRY_START_RE.match(mm, pos) and (m := _TIMESTAMP_RE.match(mm, pos)):
            try:
                return datetime.fromisoformat(m.group(1).decode()).replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                return None
        if pos <= lowest:
            return None
        newline = mm.rfind(b"\n", lowest, pos - 1)
        pos = newline + 1 if newline != -1 else lowest
