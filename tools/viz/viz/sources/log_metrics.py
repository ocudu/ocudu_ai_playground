# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Source type for the METRICS lines of OCUDU logs."""

from __future__ import annotations

from datetime import timezone
from importlib import metadata
from pathlib import Path

from parsers.log import metrics, preamble

from .base import DatasetWriter, ProgressFn

# Fields that identify the entity a metric belongs to, besides the ones in the line context.
_IDENTITY_FIELDS = ("du", "ue", "rb", "drb")
# Display label and instance field of the datasets that are not shown by their layer name.
_DATASET_INFO = {"exec": {"label": "executors", "instance": "executor"}}
# Lines between two registered record offsets.
_OFFSET_INTERVAL = 1000
# Bytes between two progress reports.
_PROGRESS_INTERVAL = 8 << 20


def _parsers_version() -> str:
    try:
        return metadata.version("ocudu-parsers")
    except metadata.PackageNotFoundError:
        return "unknown"


class LogMetricsSource:
    """One time series dataset per METRICS layer. Records are log lines, identified by line number."""

    name = "log_metrics"
    version = f"1+parsers-{_parsers_version()}"

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
        parser = metrics.MetricsParser()
        total = path.stat().st_size
        offset = 0
        next_progress = 0
        with path.open("rb") as f:
            for line_no, raw in enumerate(f, start=1):
                if line_no % _OFFSET_INTERVAL == 1:
                    writer.add_record_offset(line_no, offset)
                offset += len(raw)
                if progress and offset >= next_progress:
                    progress(offset, total)
                    next_progress = offset + _PROGRESS_INTERVAL

                # Cheap check before decoding, most lines are not metrics.
                if b"[METRICS" not in raw:
                    continue
                rec = parser.parse(raw.decode("utf-8", "replace"))
                if rec is None:
                    continue
                layer = rec.pop("layer")
                # Log timestamps carry no zone, so they are stored as UTC wall clock.
                t = rec.pop("timestamp").replace(tzinfo=timezone.utc).timestamp()
                writer.add_row(layer, line_no, t, rec)

        if progress:
            progress(total, total)
        for layer, units in parser.units.items():
            context = list(dict.fromkeys([*metrics.LAYER_PATTERNS[layer].groupindex, *_IDENTITY_FIELDS]))
            writer.set_dataset_info(layer, units, context, **_DATASET_INFO.get(layer, {}))
