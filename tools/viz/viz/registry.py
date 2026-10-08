# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Open runs and their sources, including the sources being parsed in the background."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from parsers.log.run import log_run, same_run

from .files import resolve_within
from .sources.base import SourceType
from .store import Store, StoreCache


# Supported files a directory run may have, beyond which its files are opened on their own.
MAX_RUN_FILES = 20


class OpenError(ValueError):
    """A file that cannot be opened as a source."""


@dataclass
class SourceEntry:
    """One source and its state: "parsing", "ready", "error" or "closed".

    Events are parsed once the source is ready, with their own state: "pending", "parsing", "ready" or "error".
    """

    id: int
    path: Path
    status: str
    progress: float = 0.0
    error: str | None = None
    store: Store | None = None
    events_status: str = "pending"
    source_type: SourceType | None = None


@dataclass
class RunEntry:
    """Sources shown together: the supported files of a directory, or a single file. Status "open" or "closed"."""

    id: int
    path: Path
    is_dir: bool
    source_ids: list[int]
    status: str = "open"

    @property
    def directory(self) -> Path:
        """Directory whose files the run may hold."""
        return self.path if self.is_dir else self.path.parent


class SourceRegistry:
    """Runs and sources by id, in opening order. Ids are positions and never reused."""

    def __init__(self, cache: StoreCache | None = None, source_types: list[SourceType] | None = None, roots: list[Path] | None = None):
        """Without a cache, only the sources added with add_store() are served."""
        self.cache = cache
        self.source_types = source_types or []
        self.roots = roots or []
        self._entries: list[SourceEntry] = []
        self._runs: list[RunEntry] = []
        # Guards _entries and _runs, which background parsing threads update.
        self._lock = threading.Lock()

    def add_store(self, store: Store, source_type: SourceType | None = None) -> SourceEntry:
        """Adds a source parsed before the server started. With its source type, its events are parsed in the
        background, unless the store serves them already.
        """
        with self._lock:
            entry = SourceEntry(len(self._entries), store.path, "ready", 1.0, store=store, source_type=source_type)
            if store.events_ready:
                entry.events_status = "ready"
            self._entries.append(entry)
        if not store.events_ready and source_type is not None and self.cache is not None:
            threading.Thread(target=self._parse_events, args=(entry, source_type, store), daemon=True, name=f"events-{entry.id}").start()
        return entry

    def add_run(self, path: Path, is_dir: bool, source_ids: list[int]) -> RunEntry:
        """Adds a run of sources already added, e.g. with add_store()."""
        with self._lock:
            run = RunEntry(len(self._runs), path, is_dir, list(source_ids))
            self._runs.append(run)
        return run

    def open_run(self, path: str | Path) -> RunEntry:
        """Opens a directory within the roots as a run of its supported files, or a file as a run of that file.

        The sources are parsed in the background. A run already open is not reopened.
        """
        if self.cache is None:
            raise OpenError("Opening files is not available.")
        resolved = resolve_within(path, self.roots)
        is_dir = resolved.is_dir()
        with self._lock:
            for run in self._runs:
                if run.status == "open" and run.path == resolved and run.is_dir == is_dir:
                    return run
        if is_dir:
            files = self.supported_files(resolved)
            if not files:
                raise OpenError(f"{path}: no supported files in the directory.")
            if len(files) > MAX_RUN_FILES:
                raise OpenError(
                    f"{path}: {len(files)} supported files, more than the {MAX_RUN_FILES} of a run. Open its files on their own."
                )
        else:
            files = [resolved]
        source_ids = [self.open(f).id for f in files]
        return self.add_run(resolved, is_dir, source_ids)

    def supported_files(self, directory: Path) -> list[Path]:
        """The files of a directory that a source type accepts, by name."""
        try:
            files = sorted(p for p in directory.iterdir() if p.is_file())
        except OSError as e:
            raise OpenError(f"{directory}: {e.strerror or e}.") from None
        return [f for f in files if any(st.accepts(f) for st in self.source_types)]

    def add_to_run(self, run_id: int, path: str | Path) -> RunEntry:
        """Adds a file of the directory of a run to the run. Raises KeyError for unknown ids."""
        run = self._run(run_id)
        resolved = resolve_within(path, self.roots)
        if resolved.parent != run.directory:
            raise OpenError(f"{path}: not in the directory of the run, {run.directory}.")
        entry = self.open(resolved)
        with self._lock:
            if entry.id not in run.source_ids:
                run.source_ids.append(entry.id)
        return run

    def related_files(self, run_id: int) -> list[Path]:
        """The supported files of the directory of a run, not in it, written by the same run as one of its files.

        Files of the same run have the same build and overlapping time spans, see parsers.log.run.same_run().
        """
        run = self._run(run_id)
        with self._lock:
            in_run = {self._entries[i].path for i in run.source_ids}
        identities = [i for p in in_run if (i := log_run(p)) is not None]
        if not identities:
            return []
        related = []
        for f in self.supported_files(run.directory):
            if f.resolve() in in_run:
                continue
            other = log_run(f)
            if other is not None and any(same_run(i, other) for i in identities):
                related.append(f)
        return related

    def promote_run(self, run_id: int) -> RunEntry:
        """Adds the related files of a run, see related_files(), and makes it the run of its directory.

        If the directory is open as a run already, closes this run and returns that one instead. Raises KeyError for
        unknown ids.
        """
        run = self._run(run_id)
        with self._lock:
            existing = next(
                (r for r in self._runs if r.status == "open" and r.is_dir and r.path == run.directory and r is not run),
                None,
            )
        if existing is not None:
            self.close_run(run_id)
            return existing
        for f in self.related_files(run_id):
            self.add_to_run(run_id, f)
        with self._lock:
            run.path, run.is_dir = run.directory, True
        return run

    def remove_from_run(self, run_id: int, source_id: int) -> RunEntry:
        """Removes a source from a run, closing it unless another open run has it. A run left empty is closed.

        Raises KeyError for unknown ids.
        """
        run = self._run(run_id)
        with self._lock:
            if source_id in run.source_ids:
                run.source_ids.remove(source_id)
            if not run.source_ids:
                run.status = "closed"
        self._close_unused([source_id])
        return run

    def close_run(self, run_id: int) -> None:
        """Closes a run, and its sources that no other open run has. Raises KeyError for unknown ids."""
        run = self._run(run_id)
        with self._lock:
            run.status = "closed"
        self._close_unused(run.source_ids)

    def runs(self) -> list[RunEntry]:
        """Returns the runs in id order."""
        with self._lock:
            return list(self._runs)

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
            entry = SourceEntry(len(self._entries), resolved, "parsing", source_type=source_type)
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

    def source_type(self, source_id: int) -> SourceType | None:
        """Returns the source type of a source, None if unknown. Raises KeyError for unknown ids."""
        with self._lock:
            if not 0 <= source_id < len(self._entries):
                raise KeyError(source_id)
            return self._entries[source_id].source_type

    def _run(self, run_id: int) -> RunEntry:
        with self._lock:
            if not 0 <= run_id < len(self._runs) or self._runs[run_id].status != "open":
                raise KeyError(run_id)
            return self._runs[run_id]

    def _close_unused(self, source_ids: list[int]) -> None:
        with self._lock:
            used = {s for run in self._runs if run.status == "open" for s in run.source_ids}
        for source_id in source_ids:
            if source_id not in used:
                self.close(source_id)

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
            if entry.status != "parsing":
                return
            entry.store, entry.status, entry.progress = store, "ready", 1.0
        self._parse_events(entry, source_type, store)

    def _parse_events(self, entry: SourceEntry, source_type: SourceType, store: Store) -> None:
        entry.events_status = "parsing"
        try:
            self.cache.open_events(store, source_type)
        except Exception:
            # Failing events leave the datasets of the source usable.
            entry.events_status = "error"
            return
        entry.events_status = "ready"
