# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Source type for the METRICS lines of OCUDU logs."""

from __future__ import annotations

import logging
import mmap
import re
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from parsers.log import config, events, metrics, preamble

from .. import parallel
from .base import DatasetWriter, EventWriter, ProgressFn

logger = logging.getLogger("parsers")

# Fields that identify the entity a metric belongs to, besides the ones in the line context.
_IDENTITY_FIELDS = ("du", "ue", "rb", "drb")
# Display label and instance field of the datasets that are not shown by their layer name.
_DATASET_INFO = {"exec": {"label": "executors", "instance": "executor"}}
# Lines between two registered record offsets.
_OFFSET_INTERVAL = 1000
# Logs from this size have their metrics parsed in chunks, in parallel.
_PARALLEL_MIN_SIZE = 16 << 20
# Smallest chunk, and chunks per worker, so that a slow chunk does not hold back the following ones for long.
_MIN_CHUNK_SIZE = 4 << 20
_CHUNKS_PER_WORKER = 4
_EVENT_CANDIDATE_RE = re.compile(events.CANDIDATE_PATTERN.encode())
_ENTRY_START_RE = re.compile(events.ENTRY_START_PATTERN.encode())
# Log level options of the layers whose info lines hold the UE events, with the events they hold.
_EVENT_LEVEL_OPTIONS = {
    "mac": "random access, RLF",
    "du": "UE creation and deletion",
    "rrc": "RRC messages, reestablishment",
    "cu": "handover",
    "ngap": "handover preparation",
}
# Bytes read from the end of the log to find its last timestamp.
_TAIL_SIZE = 64 << 10


def _epoch(timestamp: str) -> float | None:
    """Seconds since the epoch of a log timestamp, stored as UTC wall clock since logs carry no zone."""
    try:
        return datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def _last_timestamp(path: Path) -> float | None:
    with path.open("rb") as f:
        f.seek(max(0, path.stat().st_size - _TAIL_SIZE))
        lines = f.read().decode("utf-8", "replace").splitlines()
    for line in reversed(lines):
        m = preamble.match_preamble(line)
        if m and (t := _epoch(m.group("timestamp"))) is not None:
            return t
    return None


def _event_notes(path: Path) -> list[str]:
    """Notes about the UE events that the log levels of the log exclude, from its configuration echo."""
    with path.open(encoding="utf-8", errors="replace") as f:
        cfg = config.from_log(f)
    if cfg is None:
        return []
    info = config.LEVELS.index("info")
    quiet = [(option, held) for option, held in _EVENT_LEVEL_OPTIONS.items() if config.LEVELS.index(cfg.level(option)) < info]
    if not quiet:
        return []
    by_level: dict[str, list[str]] = {}
    for option, _ in quiet:
        by_level.setdefault(cfg.level(option), []).append(option)
    levels = "; ".join(f"{', '.join(options)} at {level}" for level, options in by_level.items())
    held = ", ".join(held for _, held in quiet)
    return [f"Some UE events are not in the log, whose layers log below info ({levels}): {held}."]


def _parse_metrics_chunk(path: str, start: int, end: int) -> dict[str, Any]:
    """Parses the metrics of the byte range [start, end) of a log, which starts at a line.

    Returns the number of lines of the range, record offsets and rows by line number within the range from 1, the
    first timestamp and the units seen. Rows are grouped by layer, each with the index of its field names in the
    shapes of the layer, to keep the result small.
    """
    result: dict[str, Any] = {"nof_lines": 0, "offsets": [], "first_t": None, "units": {}, "layers": {}}
    if end <= start:
        return result
    with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        data = mm[start:end]
    lines = data.split(b"\n")
    if lines[-1] == b"":
        lines.pop()

    parser = metrics.MetricsParser()
    layers: dict[str, tuple[list[tuple], dict[tuple, int], list[tuple]]] = {}
    first_t = None
    offset = start
    for line_no, raw in enumerate(lines, start=1):
        if line_no % _OFFSET_INTERVAL == 1:
            result["offsets"].append((line_no, offset))
        offset += len(raw) + 1
        if first_t is None and (m := preamble.match_preamble(raw.decode("utf-8", "replace"))):
            first_t = _epoch(m.group("timestamp"))
        # Cheap check before decoding, most lines are not metrics.
        if b"[METRICS" not in raw:
            continue
        rec = parser.parse(raw.decode("utf-8", "replace"))
        if rec is None:
            continue
        layer = rec.pop("layer")
        t = rec.pop("timestamp").replace(tzinfo=timezone.utc).timestamp()
        shapes, shape_ids, rows = layers.setdefault(layer, ([], {}, []))
        shape = tuple(rec)
        shape_id = shape_ids.get(shape)
        if shape_id is None:
            shape_id = shape_ids[shape] = len(shapes)
            shapes.append(shape)
        rows.append((line_no, t, shape_id, tuple(rec.values())))

    result["nof_lines"] = len(lines)
    result["first_t"] = first_t
    result["units"] = parser.units
    result["layers"] = {layer: (shapes, rows) for layer, (shapes, _, rows) in layers.items()}
    return result


def _parsers_version() -> str:
    try:
        return metadata.version("ocudu-parsers")
    except metadata.PackageNotFoundError:
        return "unknown"


class LogMetricsSource:
    """One time series dataset per METRICS layer, and the events of the log. Records are log lines, identified by
    line number.
    """

    name = "log_metrics"
    version = f"3+parsers-{_parsers_version()}"

    def accepts(self, path: Path) -> bool:
        try:
            with path.open("rb") as f:
                head = f.read(64 << 10)
        except OSError:
            return False
        if b"\0" in head:
            return False
        return any(preamble.match_preamble(line) for line in head.decode("utf-8", "replace").splitlines()[:200])

    def parse(self, path: Path, writer: DatasetWriter, progress: ProgressFn | None = None) -> None:
        writer.set_notes(_event_notes(path))
        total = path.stat().st_size
        nof_chunks = 1
        if total >= _PARALLEL_MIN_SIZE:
            nof_chunks = max(1, min(parallel.nof_workers() * _CHUNKS_PER_WORKER, total // _MIN_CHUNK_SIZE))
        ranges = parallel.chunk_ranges(path, nof_chunks, _ENTRY_START_RE)
        results = parallel.map_chunks(_parse_metrics_chunk, [(str(path), start, end) for start, end in ranges])

        # Results come in file order, so line numbers continue from the previous chunks, and units seen first win
        # as in a single pass.
        all_units: dict[str, dict[str, str]] = {layer: {} for layer in metrics.LAYER_PATTERNS}
        warned: set[tuple[str, str]] = set()
        first_t = None
        lines_before = 0
        for (_, end), res in zip(ranges, results):
            for line_no, offset in res["offsets"]:
                writer.add_record_offset(lines_before + line_no, offset)
            for layer, (shapes, rows) in res["layers"].items():
                for line_no, t, shape_id, values in rows:
                    writer.add_row(layer, lines_before + line_no, t, dict(zip(shapes[shape_id], values)))
            for layer, chunk_units in res["units"].items():
                for field, unit in chunk_units.items():
                    known = all_units[layer].setdefault(field, unit)
                    if known != unit and (layer, field) not in warned:
                        warned.add((layer, field))
                        logger.warning(f"Field {layer}.{field} has unit {unit!r}, expected {known!r}.")
            if first_t is None:
                first_t = res["first_t"]
            lines_before += res["nof_lines"]
            if progress:
                progress(end, total)

        last_t = _last_timestamp(path)
        if first_t is not None and last_t is not None:
            writer.set_time_range(first_t, last_t)
        for layer, units in all_units.items():
            context = list(dict.fromkeys([*metrics.LAYER_PATTERNS[layer].groupindex, *_IDENTITY_FIELDS]))
            writer.set_dataset_info(layer, units, context, **_DATASET_INFO.get(layer, {}))

    def parse_events(self, path: Path, writer: EventWriter) -> None:
        # Header line number, line, preamble match and continuation lines of the entry whose events are pending.
        pending: tuple[int, str, re.Match, list[str]] | None = None
        tracker = events.UeTracker()

        def add_events(line_no: int, line: str, m: re.Match, body: list[str]) -> None:
            for ev in events.parse(line, body, m):
                ev["lane"] = tracker.assign(ev)
                ev_t = ev.pop("timestamp").replace(tzinfo=timezone.utc).timestamp()
                writer.add_event(line_no, ev_t, ev)

        with path.open("rb") as f:
            for line_no, raw in enumerate(f, start=1):
                if pending is not None:
                    if not _ENTRY_START_RE.match(raw):
                        pending[3].append(raw.decode("utf-8", "replace"))
                        continue
                    add_events(*pending)
                    pending = None
                # Cheap check before decoding, most lines are not events.
                if not _EVENT_CANDIDATE_RE.search(raw):
                    continue
                line = raw.decode("utf-8", "replace")
                if m := preamble.match_preamble(line):
                    if events.has_body(m):
                        pending = (line_no, line, m, [])
                    else:
                        add_events(line_no, line, m, [])
        if pending is not None:
            add_events(*pending)
        for lane in tracker.lanes:
            writer.add_lane(lane.id, lane.du_ue, lane.rnti)
