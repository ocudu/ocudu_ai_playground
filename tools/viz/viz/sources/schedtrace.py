# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Source type of the scheduler event traces of OCUDU (schedtrace_cell<N>.bin): the resource grid of their cell."""

from __future__ import annotations

import json
import mmap
import re
import struct
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from parsers import schedtrace
from parsers.schedtrace import grid as grid_util

from .. import parallel
from .base import DatasetWriter, ProgressFn, RunIdentity
from .log_metrics import _parsers_version

_NAME_RE = re.compile(r"schedtrace_cell\d+\.bin")
# CRBs of a row of the occupancy grid.
GROUP_SIZE = 4
# Slots of the bins of the stored occupancy, from the finest.
LEVELS = (20, 100, 400, 2000)
# A window of at most this many slots shows its allocations, and of at most SLOT_HEAT_MAX slots its occupancy per slot,
# both decoded from the trace; larger windows show the stored occupancy.
RECTS_MAX = 400
SLOT_HEAT_MAX = 4000
# Events per chunk parsed in the worker pool.
_CHUNK_EVENTS = 20000
# Share of the slots with allocations that have both DL and UL shared or control channels from which the cell is
# taken as FDD: TDD only mixes them in special slots, without PDSCH and PUSCH together.
_FDD_MIN_SHARE = 0.05
_U32 = struct.Struct("<I")
# Frames after which the SFN wraps.
_NOF_SFNS = 1024


class SchedtraceSource:
    """The resource grid of the cell of a scheduler event trace. Records are its events, the slots among them in the
    grid, with a summary as text and their decoding as detail.
    """

    name = "schedtrace"
    # The schema hash invalidates the parses of the trace when the schemas change.
    version = f"4+parsers-{_parsers_version()}+schema-{schedtrace.schema_hash()[:12]}"

    def accepts(self, path: Path) -> bool:
        if not _NAME_RE.fullmatch(path.name):
            return False
        try:
            with path.open("rb") as f:
                head = f.read(4)
            return len(head) == 4 and _U32.unpack(head)[0] <= path.stat().st_size
        except OSError:
            return False

    def on_request(self, path: Path) -> bool:
        """Whether a trace is parsed only on request with the other files of its run: always, since they are large."""
        return True

    def run_identity(self, path: Path) -> RunIdentity | None:
        with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            offsets = schedtrace.offsets(mm)
            if not offsets:
                return None
            first = schedtrace.event_at(mm, offsets[0])["timestamp_us"] / 1e6
            last = schedtrace.event_at(mm, offsets[-1])["timestamp_us"] / 1e6
        return RunIdentity(None, first, last)

    def parse(self, path: Path, writer: DatasetWriter, progress: ProgressFn | None = None) -> None:
        with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            offsets = schedtrace.offsets(mm)
            if not offsets:
                return
            start = schedtrace.event_at(mm, offsets[0])
        cell = grid_util.cell_of(start) if start["type"] == "CellStartEvent" else None
        if cell is None:
            raise ValueError(f"{path.name}: the trace does not start with the start event of its cell.")
        size = path.stat().st_size
        # Chunks of whole events, each parsed in the pool with the record of its first event.
        bounds = [*offsets[::_CHUNK_EVENTS], offsets[-1] + 4 + _event_size(path, offsets[-1])]
        args = [(str(path), lo, hi, 1 + i * _CHUNK_EVENTS, _cell_dict(cell)) for i, (lo, hi) in enumerate(zip(bounds, bounds[1:]))]
        bins: dict[tuple[int, int], dict[str, Any]] = {}
        mixed = Counter()
        t_min = t_max = None
        for (_, _, hi, _, _), res in zip(args, parallel.map_chunks(_parse_chunk, args)):
            writer.add_record_texts(res["texts"])
            writer.add_grid_slots(res["slots"])
            mixed.update(res["mixed"])
            for key, b in res["bins"].items():
                into = bins.setdefault(key, {"t0": b["t0"], "t1": b["t1"], "n": 0, "occ": Counter()})
                into["t0"], into["t1"] = min(into["t0"], b["t0"]), max(into["t1"], b["t1"])
                into["n"] += b["n"]
                into["occ"].update(b["occ"])
            if res["t_min"] is not None:
                t_min = res["t_min"] if t_min is None else min(t_min, res["t_min"])
                t_max = res["t_max"] if t_max is None else max(t_max, res["t_max"])
            if progress:
                progress(hi, size)
        writer.add_grid_cells([
            (level, index, b["t0"], b["t1"], grp, channel, occ / b["n"])
            for (level, index), b in bins.items()
            for (grp, channel), occ in b["occ"].items()
        ])
        active = mixed["dl"] + mixed["ul"] + mixed["both"]
        duplex = "FDD" if active and mixed["both"] / active >= _FDD_MIN_SHARE else "TDD"
        writer.set_meta("grid", {**_cell_dict(cell), "nof_crbs": cell.nof_crbs, "slot_duration_s": cell.slot_duration_s,
                                 "slots_per_frame": round(0.01 / cell.slot_duration_s),
                                 "duplex": duplex, "group_size": GROUP_SIZE, "cell_id": start.get("pci")})
        if t_min is not None:
            writer.set_time_range(t_min, t_max + cell.slot_duration_s)

    def record_detail(self, path: Path, record: int) -> str:
        """The decoding of an event, as JSON."""
        return json.dumps(self.record_data(path, record), indent=1)

    def record_data(self, path: Path, record: int) -> dict[str, Any]:
        """The decoding of an event, as schedtrace.read() gives it."""
        offsets = _offsets(str(path), path.stat().st_mtime_ns)
        if not 1 <= record <= len(offsets):
            raise ValueError(f"No event {record}.")
        with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            return schedtrace.event_at(mm, offsets[record - 1])

    def grid(self, path: Path, store: Any, t0: float | None, t1: float | None, width: int) -> dict[str, Any]:
        """The resource grid of a time window for a chart width in pixels, with "anchors", slots as [time, slot_tx], to
        label time in SFN.slot: its allocations ("rects"), for at most RECTS_MAX slots, else its occupancy ("cells") per
        slot, for at most SLOT_HEAT_MAX slots, else per bin of the finest stored level with at most one bin per pixel.

        The slots of the anchors, allocations and occupancy per slot are placed on a grid of slot duration by their
        slot_tx, see _slot_times(), rather than at their timestamps, which jitter with the time the events were made.
        """
        meta = store.meta["grid"]
        cell = grid_util.Cell(meta["dl_bwp"], meta["ul_bwp"], meta["pucch_resources"])
        duration = meta["slot_duration_s"]
        out: dict[str, Any] = {"cell": meta}
        count, rows = store.grid_slots(t0, t1, SLOT_HEAT_MAX)
        out["nof_slots"] = count
        wrap = _NOF_SFNS * meta["slots_per_frame"]
        # Slots of known slot_tx, to label the time axis in SFN.slot: all of the window, or about one per pixel.
        every = max(1, count // max(1, width))
        if count <= SLOT_HEAT_MAX:
            rects, cells = [], []
            times = _slot_times([(r[1], r[4]) for r in rows], duration, wrap)
            # From the slots drawn, so that the ticks fall on their boundaries.
            out["anchors"] = [[t, r[4]] for t, r in list(zip(times, rows))[::every]]
            with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                for (record, _, offset, _, _), t in zip(rows, times):
                    allocs = grid_util.allocations(schedtrace.event_at(mm, offset), cell)
                    if count <= RECTS_MAX:
                        rects.extend({**a, "t": t, "t1": t + duration, "record": record} for a in allocs)
                    else:
                        for (grp, channel), occ in grid_util.occupancy(allocs, GROUP_SIZE).items():
                            cells.append([t, t + duration, grp, channel, occ])
            if count <= RECTS_MAX:
                return {**out, "mode": "rects", "rects": rects}
            return {**out, "mode": "cells", "level": 1, "cells": cells}
        anchors = store.grid_anchors(t0, t1, every)
        out["anchors"] = [[t, a[2]] for t, a in zip(_slot_times([(a[0], a[2]) for a in anchors], duration, wrap), anchors)]
        level = next((lv for lv in LEVELS if count / lv <= max(1, width)), LEVELS[-1])
        return {**out, "mode": "cells", "level": level, "cells": [list(c) for c in store.grid_cells(level, t0, t1)]}


def _slot_times(slots: list[tuple[float, int]], duration: float, wrap: int) -> list[float]:
    """Times of slots, given as (timestamp, slot_tx) in time order, on a grid of slot duration: each at its slot count,
    slot_tx unwrapped across SFN wraps, times the duration, plus the median difference between the timestamps and
    that grid, which keeps the slots at the times of the window.
    """
    counts = []
    unwrapped = 0
    last = None
    for _, slot_tx in slots:
        if last is not None and slot_tx + unwrapped < last - wrap // 2:
            unwrapped += wrap
        last = slot_tx + unwrapped
        counts.append(last)
    if not counts:
        return []
    diffs = sorted(t - c * duration for (t, _), c in zip(slots, counts))
    offset = diffs[len(diffs) // 2]
    return [offset + c * duration for c in counts]


def _cell_dict(cell: grid_util.Cell) -> dict[str, Any]:
    return {"dl_bwp": cell.dl_bwp, "ul_bwp": cell.ul_bwp, "pucch_resources": cell.pucch_resources}


def _event_size(path: Path, offset: int) -> int:
    with path.open("rb") as f:
        f.seek(offset)
        return _U32.unpack(f.read(4))[0]


@lru_cache(maxsize=4)
def _offsets(path: str, mtime_ns: int) -> list[int]:
    """The event offsets of a trace, cached while the file is unchanged."""
    with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        return schedtrace.offsets(mm)


def _summary(event: dict[str, Any], allocs: list[dict[str, Any]], slots_per_frame: int) -> str:
    """One line of an event for the record pane, its slot in SFN.slot."""
    t = datetime.fromtimestamp(event["timestamp_us"] / 1e6, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
    if event["type"] != "CellSlotEvent":
        return f"{t} {event['type']}"
    counts = Counter(a["channel"] for a in allocs)
    inputs = Counter(i["type"] for i in event.get("inputs") or [] if i)
    parts = [f"{n}x{ch}" for ch, n in counts.items()] + [f"{n}x{name.removesuffix('Event')}" for name, n in inputs.items()]
    sfn, slot = divmod(event["slot_tx"], slots_per_frame)
    return f"{t} slot={sfn}.{slot} latency={event['latency_us']}us " + " ".join(parts)


def _parse_chunk(path: str, start: int, end: int, first_record: int, cell_dict: dict[str, Any]) -> dict[str, Any]:
    """Parses the events of the byte range [start, end) of a trace, the first being record first_record: their texts,
    the grid slots, the occupancy of the bins of LEVELS they fall in, and how many slots have DL, UL or both shared or
    control channels.
    """
    cell = grid_util.Cell(**cell_dict)
    duration = cell.slot_duration_s
    spf = round(0.01 / duration)
    texts, slots = [], []
    bins: dict[tuple[int, int], dict[str, Any]] = {}
    mixed: Counter = Counter()
    t_min = t_max = None
    with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        for i, offset in enumerate(schedtrace.offsets(mm, start, end)):
            record = first_record + i
            event = schedtrace.event_at(mm, offset)
            t = event["timestamp_us"] / 1e6
            t_min = t if t_min is None else min(t_min, t)
            t_max = t if t_max is None else max(t_max, t)
            if event["type"] != "CellSlotEvent":
                texts.append((record, _summary(event, [], spf)))
                continue
            allocs = grid_util.allocations(event, cell)
            texts.append((record, _summary(event, allocs, spf)))
            slots.append((record, t, offset, _U32.unpack_from(mm, offset)[0] + 4, event["slot_tx"]))
            dirs = {a["dir"] for a in allocs if a["channel"] in ("PDSCH", "PUSCH", "PUCCH")}
            if dirs:
                mixed["both" if len(dirs) == 2 else dirs.pop().lower()] += 1
            occ = grid_util.occupancy(allocs, GROUP_SIZE)
            for level in LEVELS:
                b = bins.setdefault((level, record // level), {"t0": t, "t1": t + duration, "n": 0, "occ": Counter()})
                b["t0"], b["t1"] = min(b["t0"], t), max(b["t1"], t + duration)
                b["n"] += 1
                b["occ"].update(occ)
    return {"texts": texts, "slots": slots, "bins": bins, "mixed": mixed, "t_min": t_min, "t_max": t_max}
