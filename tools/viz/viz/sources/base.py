# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Interface between source types and the dataset store."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

# Called with (bytes_done, bytes_total) while a source is parsed.
ProgressFn = Callable[[int, int], None]


class DatasetWriter(Protocol):
    """Sink for the datasets extracted from a source."""

    def add_row(self, dataset: str, record: int, t: float, fields: dict[str, Any]) -> None:
        """Adds one time series row. t is in seconds since the epoch, record identifies the raw record."""

    def set_dataset_info(
        self,
        dataset: str,
        units: dict[str, str],
        context: list[str],
        label: str | None = None,
        instance: str | None = None,
    ) -> None:
        """Sets the field units, context fields, display label and instance field of a time series dataset.

        The instance field identifies the entity each row belongs to (e.g. the executor name).
        """

    def set_time_range(self, t_min: float, t_max: float) -> None:
        """Sets the time span of the source, which may be wider than the span of its datasets."""

    def add_record_offset(self, record: int, offset: int) -> None:
        """Registers the byte offset where a raw record starts. Not every record needs one."""


class SourceType(Protocol):
    """Adapter from one artifact kind to datasets."""

    # Unique name, part of the cache key.
    name: str
    # Bumped when the extracted datasets change, part of the cache key.
    version: str

    def accepts(self, path: Path) -> bool:
        """Returns whether this source type can read the file."""

    def parse(self, path: Path, writer: DatasetWriter, progress: ProgressFn | None = None) -> None:
        """Extracts the datasets of the file into writer."""
