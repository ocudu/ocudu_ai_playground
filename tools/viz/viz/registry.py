# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Open sources, including the ones being parsed in the background."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from .files import resolve_within
from .sources.base import SourceType
from .store import Store, StoreCache


class OpenError(ValueError):
    """A file that cannot be opened as a source."""


@dataclass
class SourceEntry:
    """One source and its state: "parsing", "ready", "error" or "closed"."""

    id: int
    path: Path
    status: str
    progress: float = 0.0
    error: str | None = None
    store: Store | None = None


class SourceRegistry:
    """Sources by id, in opening order. Ids are positions and never reused."""

    def __init__(self, cache: StoreCache | None = None, source_types: list[SourceType] | None = None, roots: list[Path] | None = None):
        """Without a cache, only the sources added with add_store() are served."""
        self.cache = cache
        self.source_types = source_types or []
        self.roots = roots or []
        self._entries: list[SourceEntry] = []
        # Guards _entries, which background parsing threads update.
        self._lock = threading.Lock()

    def add_store(self, store: Store) -> SourceEntry:
        """Adds a source parsed before the server started."""
        with self._lock:
            entry = SourceEntry(len(self._entries), store.path, "ready", 1.0, store=store)
            self._entries.append(entry)
            return entry

    def open(self, path: str | Path) -> SourceEntry:
        """Opens a file within the roots, parsing it in the background. A file already open is not reopened."""
        if self.cache is None:
            raise OpenError("Opening files is not available.")
        resolved = resolve_within(path, self.roots)
        if not resolved.is_file():
            raise OpenError(f"{path}: not a file.")
        source_type = next((st for st in self.source_types if st.accepts(resolved)), None)
        if source_type is None:
            raise OpenError(f"{path}: unsupported file type.")
        with self._lock:
            for entry in self._entries:
                if entry.path == resolved and entry.status in ("parsing", "ready"):
                    return entry
            entry = SourceEntry(len(self._entries), resolved, "parsing")
            self._entries.append(entry)
        threading.Thread(target=self._parse, args=(entry, source_type), daemon=True, name=f"parse-{entry.id}").start()
        return entry

    def close(self, source_id: int) -> None:
        """Closes a source, releasing its store. Its id is not reused. Raises KeyError for unknown ids."""
        with self._lock:
            if not 0 <= source_id < len(self._entries):
                raise KeyError(source_id)
            entry = self._entries[source_id]
            entry.status, entry.store = "closed", None

    def entries(self) -> list[SourceEntry]:
        """Returns the sources in id order."""
        with self._lock:
            return list(self._entries)

    def get_ready(self, source_id: int) -> Store | None:
        """Returns the store of a parsed source, or None if it is not parsed yet. Raises KeyError for unknown ids."""
        with self._lock:
            if not 0 <= source_id < len(self._entries):
                raise KeyError(source_id)
            return self._entries[source_id].store

    def _parse(self, entry: SourceEntry, source_type: SourceType) -> None:
        def progress(done: int, total: int) -> None:
            entry.progress = done / total if total else 1.0

        try:
            store = self.cache.open(entry.path, source_type, progress)
        except Exception as e:
            # Any parsing failure is reported on the source rather than crashing the server.
            with self._lock:
                if entry.status == "parsing":
                    entry.status, entry.error = "error", f"{entry.path.name}: {e}"
            return
        with self._lock:
            # A source closed while it was parsing stays closed.
            if entry.status == "parsing":
                entry.store, entry.status, entry.progress = store, "ready", 1.0
