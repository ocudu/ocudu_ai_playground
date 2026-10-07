# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Source type for the METRICS lines of OCUDU logs."""

from __future__ import annotations

import itertools
import logging
import re
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from parsers.log import chunks, config, events, metrics, preamble

from .. import parallel
from .base import DatasetWriter, EventWriter, ProgressFn, column_type, column_value

logger = logging.getLogger("parsers")

# Fields that identify the entity a metric belongs to, besides the ones in the line context.
_IDENTITY_FIELDS = ("du", "ue", "rb", "drb")
# Display label and instance field of the datasets that are not shown by their layer name.
_DATASET_INFO = {"exec": {"label": "executors", "instance": "executor"}}
# Lines between two registered record offsets.
_OFFSET_INTERVAL = 1000
# Smallest chunk, so that logs under twice this size are parsed in the server process, where they parse as fast as
# with workers. And chunks per worker, so that a slow chunk does not hold back the following ones for long.
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


def _parse_metrics_chunk(path: str, start: int, end: int, first_line: int) -> dict[str, Any]:
    """Parses the metrics of the byte range [start, end) of a log, which starts at line first_line.

    Returns the record offsets, the first timestamp, the units seen and, per layer, the rows grouped by their field
    names in order of first appearance: each group with the column types of each field and the rows as tuples of
    time, line number and column values, ready to store.
    """
    result: dict[str, Any] = {"offsets": [], "first_t": None, "units": {}, "layers": {}}
    if end <= start:
        return result
    lines = chunks.read_lines(path, start, end)
    parser = metrics.MetricsParser()
    # Per layer, the groups of rows by field names: the field names, the column types of each field and the rows.
    layers: dict[str, dict[tuple, tuple[tuple, dict[str, set[str]], list[tuple]]]] = {}
    first_t = None
    offset = start
    for line_no, raw in enumerate(lines, start=first_line):
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
        groups = layers.setdefault(layer, {})
        fields = tuple(rec)
        group = groups.get(fields)
        if group is None:
            group = groups[fields] = (fields, {f: set() for f in fields}, [])
        _, types, rows = group
        values = []
        for field, value in rec.items():
            vtype = column_type(value)
            if vtype is not None:
                types[field].add(vtype)
            values.append(column_value(value))
        rows.append((t, line_no, *values))

    result["first_t"] = first_t
    result["units"] = parser.units
    result["layers"] = {layer: list(groups.values()) for layer, groups in layers.items()}
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
        workers = parallel.nof_workers()
        nof_chunks = 1 if workers == 1 else max(1, min(workers * _CHUNKS_PER_WORKER, total // _MIN_CHUNK_SIZE))
        ranges = chunks.chunk_ranges(path, nof_chunks)
        # Counted in the pool, since counting the lines of a large file takes about a second.
        counts = parallel.map_chunks(chunks.count_lines, [(str(path), start, end) for start, end in ranges[:-1]])
        first_lines = [1 + n for n in itertools.accumulate(counts, initial=0)]
        args = [(str(path), start, end, first_line) for (start, end), first_line in zip(ranges, first_lines)]
        results = parallel.map_chunks(_parse_metrics_chunk, args)

        # Results come in file order, so units seen first win as in a single pass.
        all_units: dict[str, dict[str, str]] = {layer: {} for layer in metrics.LAYER_PATTERNS}
        warned: set[tuple[str, str]] = set()
        first_t = None
        for (_, end), res in zip(ranges, results):
            for line_no, offset in res["offsets"]:
                writer.add_record_offset(line_no, offset)
            for layer, groups in res["layers"].items():
                for fields, types, rows in groups:
                    writer.add_rows(layer, fields, types, rows)
            for layer, chunk_units in res["units"].items():
                for field, unit in chunk_units.items():
                    known = all_units[layer].setdefault(field, unit)
                    if known != unit and (layer, field) not in warned:
                        warned.add((layer, field))
                        logger.warning(f"Field {layer}.{field} has unit {unit!r}, expected {known!r}.")
            if first_t is None:
                first_t = res["first_t"]
            if progress:
                progress(end, total)

        last_t = _last_timestamp(path)
        if first_t is not None and last_t is not None:
            writer.set_time_range(first_t, last_t)
        for layer, units in all_units.items():
            context = list(dict.fromkeys([*metrics.LAYER_PATTERNS[layer].groupindex, *_IDENTITY_FIELDS]))
            writer.set_dataset_info(layer, units, context, **_DATASET_INFO.get(layer, {}))

    def field_spans(self, text: str) -> dict[str, tuple[int, int]]:
        return metrics.field_spans(text)

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
