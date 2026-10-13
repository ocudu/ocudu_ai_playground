# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Ad-hoc metrics of a log: the values of a key=value field picked from its lines, as a source of their own whose
records are the lines they come from; or, without a key, the lines that match a regular expression, as events.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from parsers.log import adhoc, chunks
from parsers.ran.rnti import normalize

from .. import parallel
from .base import DatasetWriter, EventWriter, ProgressFn, column_type
from .log_metrics import _chunk_ranges, _parsers_version

# Dataset of the values.
DATASET = "adhoc"
# Category of the events of the lines that match the filter of a spec without a key.
EVENT_CATEGORY = "adhoc"


class AdhocSource:
    """The values of the key of a spec in the lines of a log, one row per value, with their split value if the spec
    has a split key. Records are the lines with values, identified by line number. A spec without a key gives the lines
    that match its filter as records and events, and no dataset.
    """

    name = "adhoc"

    def __init__(self, spec: adhoc.Spec):
        self.spec = spec
        ident = json.dumps([spec.key, spec.filter, spec.split_key]).encode()
        # The spec is part of the cache key, so that each one is cached on its own.
        self.version = f"1+parsers-{_parsers_version()}+{hashlib.sha256(ident).hexdigest()[:16]}"

    @property
    def label(self) -> str:
        """Display name of the metric, e.g. "tbs= /ue=0/ by ue", or of the lines, e.g. "lines /rlf/"."""
        parts = [f"{self.spec.key}=" if self.spec.key else "lines"]
        if self.spec.filter:
            parts.append(f"/{self.spec.filter}/")
        if self.spec.split_key:
            parts.append(f"by {self.spec.split_key}")
        return " ".join(parts)

    def accepts(self, path: Path) -> bool:
        """Never: ad-hoc metrics are opened from a log, not as files."""
        return False

    def parse(self, path: Path, writer: DatasetWriter, progress: ProgressFn | None = None) -> None:
        args = _chunk_args(path, self.spec)
        total = path.stat().st_size
        if self.spec.key is None:
            for (_, _, end, _, _), rows in zip(args, parallel.map_chunks(adhoc.scan_lines, args)):
                writer.add_record_lines([(line, offset) for _, line, offset, *_ in rows])
                if progress:
                    progress(end, total)
            return
        split = self.spec.split_key
        fields = (self.spec.key, split) if split else (self.spec.key,)
        unit = None
        last_line = 0
        for (_, _, end, _, _), res in zip(args, parallel.map_chunks(adhoc.scan, args)):
            rows = [(t, line, value, s) if split else (t, line, value) for t, line, _, value, s in res["rows"]]
            if rows:
                types = {f: {t for row in rows if (t := column_type(row[i + 2])) is not None} for i, f in enumerate(fields)}
                writer.add_rows(DATASET, fields, types, rows)
            lines = []
            # A line with several values is one record.
            for _, line, offset, _, _ in res["rows"]:
                if line != last_line:
                    lines.append((line, offset))
                    last_line = line
            writer.add_record_lines(lines)
            unit = unit or res["unit"]
            if progress:
                progress(end, total)
        writer.set_dataset_info(DATASET, {self.spec.key: unit} if unit else {}, [split] if split else [], label=self.label)

    def parse_events(self, path: Path, writer: EventWriter) -> None:
        """The lines that match the filter of a spec without a key, as events, with the text, logger, level, UE index
        and RNTI of their line. Specs with a key give none.
        """
        if self.spec.key is not None:
            return
        # The type names the regex, which hovering an event shows.
        kind = f"/{self.spec.filter}/"
        for rows in parallel.map_chunks(adhoc.scan_lines, _chunk_args(path, self.spec)):
            writer.add_event_rows([(t, line, kind, EVENT_CATEGORY, layer, level, ue, normalize(rnti), None, text, None, None, None)
                                   for t, line, _, text, layer, level, ue, rnti in rows])

    def field_spans(self, text: str) -> dict[str, tuple[int, int]]:
        """The span of the first value of the key in the text of a record."""
        if self.spec.key is None:
            return {}
        m = adhoc.value_re(self.spec.key).search(text.encode())
        if m is None:
            return {}
        # Byte offsets are character offsets for the ASCII of log lines up to the value.
        return {self.spec.key: (len(text.encode()[: m.start()].decode("utf-8", "replace")),
                                len(text.encode()[: m.end()].decode("utf-8", "replace")))}


def _chunk_args(path: Path, spec: adhoc.Spec) -> list[tuple]:
    """Arguments of the scans of the chunks of a log: (path, start, end, number of its first line, spec)."""
    ranges = _chunk_ranges(path)
    counts = parallel.map_chunks(chunks.count_lines, [(str(path), start, end) for start, end in ranges[:-1]])
    first_lines = [1]
    for n in counts:
        first_lines.append(first_lines[-1] + n)
    return [(str(path), start, end, first_line, spec) for (start, end), first_line in zip(ranges, first_lines)]
