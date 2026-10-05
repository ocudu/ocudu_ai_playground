# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""SQLite store of the datasets of a source: parse cache and query engine."""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import sqlite3
import tempfile
import urllib.parse
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from .filters import FilterError, compile_filter
from .sources.base import ProgressFn, SourceType

# Bumped when the database layout changes, part of the cache key.
SCHEMA_VERSION = 2
# Time series windows up to this many points are returned at full resolution.
MAX_FULL_RES_POINTS = 50_000
# Split values returned when none are selected.
MAX_DEFAULT_SPLITS = 20
# Bins of a histogram, unless the field has few integer values.
DEFAULT_HISTOGRAM_BINS = 50
# Windows with more points get percentiles from a sample.
MAX_EXACT_PERCENTILE_POINTS = 2_000_000

# Reserved column names of dataset tables.
_TS = "_ts"
_REC = "_rec"
# Rows buffered per dataset before an insert.
_BATCH_SIZE = 5000
_CACHE_SUFFIX = ".sqlite"

_memory_db_ids = itertools.count()


class QueryError(ValueError):
    """Invalid query arguments, e.g. an unknown dataset or field."""


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _value_type(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "text"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, (list, dict)):
        return "json"
    return "text"


class _DatasetBuffer:
    """Columns and pending rows of one dataset table being built."""

    def __init__(self, name: str):
        self.name = name
        self.columns: list[str] = []
        self.types: dict[str, str] = {}
        self.rows: list[tuple] = []


class StoreWriter:
    """Writes the datasets of a source into a SQLite database."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._datasets: dict[str, _DatasetBuffer] = {}
        self._info: dict[str, tuple[dict[str, str], list[str], str | None, str | None]] = {}
        self._time_range: tuple[float, float] | None = None
        self._conn.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE datasets (
                name TEXT PRIMARY KEY, kind TEXT, fields TEXT, units TEXT, context TEXT, label TEXT, instance TEXT
            );
            CREATE TABLE record_offsets (record INTEGER PRIMARY KEY, offset INTEGER);
            """
        )

    def add_row(self, dataset: str, record: int, t: float, fields: dict[str, Any]) -> None:
        ds = self._datasets.get(dataset)
        if ds is None:
            ds = self._datasets[dataset] = _DatasetBuffer(dataset)
            self._conn.execute(f"CREATE TABLE {_quote('ds_' + dataset)} ({_TS} REAL, {_REC} INTEGER)")

        new_columns = [k for k in fields if k not in ds.types]
        if new_columns:
            self._flush(ds)
            for col in new_columns:
                ds.columns.append(col)
                ds.types[col] = ""
                self._conn.execute(f"ALTER TABLE {_quote('ds_' + dataset)} ADD COLUMN {_quote(col)}")

        row = [t, record]
        for col in ds.columns:
            value = fields.get(col)
            vtype = _value_type(value)
            if vtype is not None and ds.types[col] != vtype:
                ds.types[col] = vtype if ds.types[col] == "" else "text"
            row.append(json.dumps(value) if vtype == "json" else value)
        ds.rows.append(tuple(row))
        if len(ds.rows) >= _BATCH_SIZE:
            self._flush(ds)

    def set_dataset_info(
        self,
        dataset: str,
        units: dict[str, str],
        context: list[str],
        label: str | None = None,
        instance: str | None = None,
    ) -> None:
        self._info[dataset] = (units, context, label, instance)

    def set_time_range(self, t_min: float, t_max: float) -> None:
        self._time_range = (t_min, t_max)

    def add_record_offset(self, record: int, offset: int) -> None:
        self._conn.execute("INSERT OR REPLACE INTO record_offsets VALUES (?, ?)", (record, offset))

    def finish(self, source_path: Path, source_type: str) -> None:
        """Flushes pending rows, writes the dataset metadata and indexes."""
        t_min = t_max = None
        for ds in self._datasets.values():
            self._flush(ds)
            table = _quote("ds_" + ds.name)
            self._conn.execute(f"CREATE INDEX {_quote('idx_' + ds.name)} ON {table} ({_TS})")
            lo, hi = self._conn.execute(f"SELECT MIN({_TS}), MAX({_TS}) FROM {table}").fetchone()
            if lo is not None:
                t_min = lo if t_min is None else min(t_min, lo)
                t_max = hi if t_max is None else max(t_max, hi)

            units, context, label, instance = self._info.get(ds.name, ({}, [], None, None))
            fields = {col: (ds.types[col] or "text") for col in ds.columns}
            self._conn.execute(
                "INSERT INTO datasets VALUES (?, 'timeseries', ?, ?, ?, ?, ?)",
                (
                    ds.name,
                    json.dumps(fields),
                    json.dumps(units),
                    json.dumps([c for c in context if c in fields]),
                    label or ds.name,
                    instance if instance in fields else None,
                ),
            )

        if self._time_range is not None:
            t_min = self._time_range[0] if t_min is None else min(t_min, self._time_range[0])
            t_max = self._time_range[1] if t_max is None else max(t_max, self._time_range[1])
        meta = {
            "path": str(source_path),
            "source_type": source_type,
            "t_min": t_min,
            "t_max": t_max,
            "complete": True,
        }
        self._conn.executemany("INSERT INTO meta VALUES (?, ?)", [(k, json.dumps(v)) for k, v in meta.items()])
        self._conn.commit()

    def _flush(self, ds: _DatasetBuffer) -> None:
        if not ds.rows:
            return
        cols = ", ".join([_TS, _REC] + [_quote(c) for c in ds.columns])
        marks = ", ".join("?" * (len(ds.columns) + 2))
        self._conn.executemany(f"INSERT INTO {_quote('ds_' + ds.name)} ({cols}) VALUES ({marks})", ds.rows)
        ds.rows.clear()


class Store:
    """Read access to the datasets of one source. Safe to use from several threads."""

    def __init__(self, uri: str, keepalive: sqlite3.Connection | None = None):
        """Opens the database at the SQLite URI. keepalive holds an in-memory database open."""
        self._uri = uri
        self._keepalive = keepalive
        with self._connect() as conn:
            self.meta = {k: json.loads(v) for k, v in conn.execute("SELECT key, value FROM meta")}
            self.datasets = {
                name: {
                    "name": name,
                    "kind": kind,
                    "fields": json.loads(fields),
                    "units": json.loads(units),
                    "context": json.loads(context),
                    "label": label,
                    "instance": instance,
                }
                for name, kind, fields, units, context, label, instance in conn.execute(
                    "SELECT name, kind, fields, units, context, label, instance FROM datasets ORDER BY label"
                )
            }

    @property
    def path(self) -> Path:
        return Path(self.meta["path"])

    def series(
        self,
        dataset: str,
        field: str,
        t0: float | None = None,
        t1: float | None = None,
        width: int = 1000,
        split_by: str | None = None,
        split_values: list[str] | None = None,
        filter_expr: str | None = None,
        instance: str | None = None,
        max_points: int = MAX_FULL_RES_POINTS,
        max_splits: int = MAX_DEFAULT_SPLITS,
    ) -> dict[str, Any]:
        """Returns the series of a numeric field, one per split value, downsampled to min/max per pixel if needed.

        Without explicit split values, only the first max_splits are returned.
        """
        ds = self._dataset(dataset)
        table = _quote("ds_" + dataset)
        value = _quote(field)
        split_col = _quote(split_by) if split_by else "NULL"
        with self._connect() as conn:
            where_sql, params, total_splits = self._window(conn, ds, field, t0, t1, split_by, split_values, filter_expr, instance, max_splits)
            count, lo, hi = conn.execute(f"SELECT COUNT(*), MIN({_TS}), MAX({_TS}) FROM {table} WHERE {where_sql}", params).fetchone()
            downsampled = count > max_points and hi is not None and hi > lo
            if not downsampled:
                rows = conn.execute(
                    f"SELECT {split_col}, {_TS}, {value}, {_REC} FROM {table} WHERE {where_sql} ORDER BY {_TS}", params
                ).fetchall()
            else:
                start = t0 if t0 is not None else lo
                end = t1 if t1 is not None else hi
                scale = width / max(end - start, 1e-9)
                # The window end would otherwise get a bucket of its own.
                bucket = f"MIN(CAST(({_TS} - ?) * ? AS INTEGER), {int(width) - 1})"
                rows = []
                # SQLite returns the other columns of the row holding the MIN or MAX.
                for agg in ("MIN", "MAX"):
                    rows += conn.execute(
                        f"SELECT {split_col}, {_TS}, {agg}({value}), {_REC} FROM {table} WHERE {where_sql} "
                        f"GROUP BY {split_col}, {bucket}",
                        params + [start, scale],
                    ).fetchall()

        by_split: dict[Any, dict[int, tuple[float, Any]]] = {}
        for g, t, v, rec in rows:
            by_split.setdefault(g, {})[rec] = (t, v)
        series = []
        for g in sorted(by_split, key=_split_sort_key):
            points = sorted(by_split[g].items(), key=lambda item: (item[1][0], item[0]))
            series.append({
                "label": _label(field, split_by, g),
                "split": g,
                "t": [p[1][0] for p in points],
                "v": [p[1][1] for p in points],
                "record": [p[0] for p in points],
            })
        return {"unit": ds["units"].get(field), "downsampled": downsampled, "total_splits": total_splits, "series": series}

    def stats(
        self,
        dataset: str,
        field: str,
        t0: float | None = None,
        t1: float | None = None,
        split_by: str | None = None,
        split_values: list[str] | None = None,
        filter_expr: str | None = None,
        instance: str | None = None,
        max_splits: int = MAX_DEFAULT_SPLITS,
        max_exact_points: int = MAX_EXACT_PERCENTILE_POINTS,
    ) -> dict[str, Any]:
        """Returns count, min, max, mean and percentiles of a numeric field per split value.

        Percentiles are estimated from an evenly spaced sample when there are more than max_exact_points.
        """
        ds = self._dataset(dataset)
        table = _quote("ds_" + dataset)
        value = _quote(field)
        split_col = _quote(split_by) if split_by else "NULL"
        with self._connect() as conn:
            where_sql, params, total_splits = self._window(conn, ds, field, t0, t1, split_by, split_values, filter_expr, instance, max_splits)
            aggregates = conn.execute(
                f"SELECT {split_col}, COUNT(*), MIN({value}), MAX({value}), AVG({value}) FROM {table} "
                f"WHERE {where_sql} GROUP BY {split_col}",
                params,
            ).fetchall()
            total = sum(row[1] for row in aggregates)
            stride = -(-total // max_exact_points) if total > max_exact_points else 1
            values: dict[Any, list[float]] = {}
            sample_sql = f"SELECT {split_col}, {value} FROM {table} WHERE {where_sql}"
            # Record ids are dense enough among metric rows for a stride to be an even sample.
            sample_params = params
            if stride > 1:
                sample_sql += f" AND {_REC} % ? = 0"
                sample_params = params + [stride]
            for g, v in conn.execute(sample_sql, sample_params):
                values.setdefault(g, []).append(v)

        series = []
        for g, count, vmin, vmax, mean in sorted(aggregates, key=lambda row: _split_sort_key(row[0])):
            pct = _percentiles(values.get(g, []), (50, 95, 99))
            series.append({
                "label": _label(field, split_by, g),
                "split": g,
                "count": count,
                "min": vmin,
                "max": vmax,
                "mean": mean,
                "p50": pct[0],
                "p95": pct[1],
                "p99": pct[2],
            })
        return {"unit": ds["units"].get(field), "sampled": stride > 1, "total_splits": total_splits, "series": series}

    def histogram(
        self,
        dataset: str,
        field: str,
        t0: float | None = None,
        t1: float | None = None,
        split_by: str | None = None,
        split_values: list[str] | None = None,
        filter_expr: str | None = None,
        instance: str | None = None,
        bins: int = DEFAULT_HISTOGRAM_BINS,
        max_splits: int = MAX_DEFAULT_SPLITS,
    ) -> dict[str, Any]:
        """Returns the value distribution of a numeric field per split value, over shared bins.

        Integer fields spanning at most bins values get one bin per integer.
        """
        ds = self._dataset(dataset)
        table = _quote("ds_" + dataset)
        value = _quote(field)
        split_col = _quote(split_by) if split_by else "NULL"
        with self._connect() as conn:
            where_sql, params, total_splits = self._window(conn, ds, field, t0, t1, split_by, split_values, filter_expr, instance, max_splits)
            lo, hi, nof_fractional = conn.execute(
                f"SELECT MIN({value}), MAX({value}), SUM({value} != CAST({value} AS INTEGER)) FROM {table} WHERE {where_sql}",
                params,
            ).fetchone()
            if lo is None:
                return {"unit": ds["units"].get(field), "edges": [], "total_splits": total_splits, "series": []}
            if not nof_fractional and hi - lo + 1 <= bins:
                start, bin_width, nof_bins = lo - 0.5, 1.0, int(hi - lo) + 1
            elif hi > lo:
                start, bin_width, nof_bins = lo, (hi - lo) / bins, bins
            else:
                start, bin_width, nof_bins = lo - 0.5, 1.0, 1
            rows = conn.execute(
                f"SELECT {split_col}, MIN(CAST(({value} - ?) / ? AS INTEGER), {nof_bins - 1}), COUNT(*) FROM {table} "
                f"WHERE {where_sql} GROUP BY 1, 2",
                [start, bin_width] + params,
            ).fetchall()

        counts: dict[Any, list[int]] = {}
        for split, b, n in rows:
            counts.setdefault(split, [0] * nof_bins)[b] += n
        series = [
            {"label": _label(field, split_by, split), "split": split, "counts": counts[split]}
            for split in sorted(counts, key=_split_sort_key)
        ]
        edges = [start + i * bin_width for i in range(nof_bins + 1)]
        return {"unit": ds["units"].get(field), "edges": edges, "total_splits": total_splits, "series": series}

    def context_values(self, dataset: str, field: str, limit: int = 1000) -> list[Any]:
        """Returns the distinct values of a field."""
        ds = self._dataset(dataset)
        if field not in ds["fields"]:
            raise QueryError(f"Unknown field {field!r} of {dataset!r}.")
        col = _quote(field)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT {col} FROM {_quote('ds_' + dataset)} WHERE {col} IS NOT NULL ORDER BY {col} LIMIT ?",
                (limit,),
            ).fetchall()
        return [r[0] for r in rows]

    def records(self, around: int, count: int = 50) -> list[dict[str, Any]]:
        """Returns the raw records (log lines) centred on the given record."""
        first = max(1, around - count // 2)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT record, offset FROM record_offsets WHERE record <= ? ORDER BY record DESC LIMIT 1", (first,)
            ).fetchone()
        record, offset = row if row else (1, 0)
        out = []
        with self.path.open("rb") as f:
            f.seek(offset)
            for raw in f:
                if record >= first:
                    out.append({"record": record, "text": raw.decode("utf-8", "replace").rstrip("\r\n")})
                    if len(out) == count:
                        break
                record += 1
        return out

    def _window(
        self,
        conn: sqlite3.Connection,
        ds: dict[str, Any],
        field: str,
        t0: float | None,
        t1: float | None,
        split_by: str | None,
        split_values: list[str] | None,
        filter_expr: str | None,
        instance: str | None,
        max_splits: int,
    ) -> tuple[str, list[Any], int]:
        """Builds the WHERE clause selecting the rows of a numeric field, returning it with its params and split count."""
        if ds["fields"].get(field) != "number":
            raise QueryError(f"Field {field!r} of {ds['name']!r} is not numeric.")
        if split_by is not None and split_by not in ds["fields"]:
            raise QueryError(f"Unknown split field {split_by!r} of {ds['name']!r}.")

        table = _quote("ds_" + ds["name"])
        split_col = _quote(split_by) if split_by else "NULL"
        where = [f"{_quote(field)} IS NOT NULL"]
        params: list[Any] = []
        if t0 is not None:
            where.append(f"{_TS} >= ?")
            params.append(t0)
        if t1 is not None:
            where.append(f"{_TS} <= ?")
            params.append(t1)
        if filter_expr and filter_expr.strip():
            try:
                cond, cond_params = compile_filter(filter_expr, ds["fields"], _quote)
            except FilterError as e:
                raise QueryError(f"Filter: {e}") from None
            where.append(cond)
            params.extend(cond_params)
        if instance is not None:
            if not ds["instance"]:
                raise QueryError(f"Dataset {ds['name']!r} has no instance field.")
            where.append(f"CAST({_quote(ds['instance'])} AS TEXT) = ?")
            params.append(instance)
        if split_by and split_values:
            where.append(f"CAST({split_col} AS TEXT) IN ({', '.join('?' * len(split_values))})")
            params.extend(split_values)

        total_splits = 1
        if split_by:
            where_sql = " AND ".join(where)
            total_splits = conn.execute(f"SELECT COUNT(DISTINCT {split_col}) FROM {table} WHERE {where_sql}", params).fetchone()[0]
            if not split_values and total_splits > max_splits:
                first = conn.execute(
                    f"SELECT DISTINCT {split_col} FROM {table} WHERE {where_sql} ORDER BY {split_col} LIMIT ?",
                    params + [max_splits],
                ).fetchall()
                where.append(f"{split_col} IN ({', '.join('?' * len(first))})")
                params.extend(r[0] for r in first)
        return " AND ".join(where), params, total_splits

    def _dataset(self, dataset: str) -> dict[str, Any]:
        try:
            return self.datasets[dataset]
        except KeyError:
            raise QueryError(f"Unknown dataset {dataset!r}.") from None

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self._uri, uri=True, check_same_thread=False)) as conn:
            yield conn


def _label(field: str, split_by: str | None, value: Any) -> str:
    return f"{split_by}={value}" if split_by else field


def _percentiles(values: list[float], percents: tuple[int, ...]) -> list[float | None]:
    """Linear interpolation percentiles, None for an empty list."""
    if not values:
        return [None] * len(percents)
    values = sorted(values)
    out = []
    for p in percents:
        pos = (len(values) - 1) * p / 100
        lo = int(pos)
        hi = min(lo + 1, len(values) - 1)
        out.append(values[lo] + (values[hi] - values[lo]) * (pos - lo))
    return out


def _split_sort_key(value: Any) -> tuple:
    if value is None:
        return (2, "")
    if isinstance(value, (int, float)):
        return (0, value)
    return (1, str(value))


def _file_uri(path: Path) -> str:
    return f"file:{urllib.parse.quote(str(path))}?mode=ro"


def _build(conn: sqlite3.Connection, path: Path, source_type: SourceType, progress: ProgressFn | None) -> None:
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    writer = StoreWriter(conn)
    source_type.parse(path, writer, progress)
    writer.finish(path, source_type.name)


def default_cache_dir() -> Path:
    """Per-user directory under the system temp dir."""
    return Path(tempfile.gettempdir()) / f"ocudu-viz-{os.getuid()}"


class StoreCache:
    """Opens sources through a directory of cached databases, evicting the least recently used ones."""

    def __init__(self, cache_dir: Path | None = None, max_bytes: int = 2 << 30, enabled: bool = True):
        self.cache_dir = cache_dir or default_cache_dir()
        self.max_bytes = max_bytes
        self.enabled = enabled

    def open(self, path: Path, source_type: SourceType, progress: ProgressFn | None = None) -> Store:
        """Returns the store of a source, parsing it if there is no valid cache."""
        path = path.resolve()
        if not self.enabled:
            uri = f"file:ocudu-viz-{os.getpid()}-{next(_memory_db_ids)}?mode=memory&cache=shared"
            keepalive = sqlite3.connect(uri, uri=True, check_same_thread=False)
            _build(keepalive, path, source_type, progress)
            return Store(uri, keepalive)

        self._make_dir()
        db = self.cache_dir / (self._key(path, source_type) + _CACHE_SUFFIX)
        if not self._is_complete(db):
            tmp = db.with_suffix(f".{os.getpid()}.tmp")
            tmp.unlink(missing_ok=True)
            conn = sqlite3.connect(tmp)
            try:
                _build(conn, path, source_type, progress)
            finally:
                conn.close()
            os.replace(tmp, db)
        # The mtime of a cache file marks its last use, for eviction.
        os.utime(db)
        self.evict(keep={db})
        return Store(_file_uri(db))

    def evict(self, keep: Iterable[Path] = ()) -> None:
        """Removes the least recently used caches until the cache dir fits in max_bytes."""
        keep = set(keep)
        files = sorted(self.cache_dir.glob("*" + _CACHE_SUFFIX), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        for p in files:
            if total <= self.max_bytes:
                break
            if p in keep:
                continue
            total -= p.stat().st_size
            p.unlink(missing_ok=True)

    def clear(self) -> None:
        """Removes all cached databases."""
        if self.cache_dir.is_dir():
            for p in self.cache_dir.glob("*" + _CACHE_SUFFIX):
                p.unlink(missing_ok=True)

    def _make_dir(self) -> None:
        self.cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    @staticmethod
    def _key(path: Path, source_type: SourceType) -> str:
        st = path.stat()
        ident = [str(path), st.st_size, st.st_mtime_ns, source_type.name, source_type.version, SCHEMA_VERSION]
        return hashlib.sha256(json.dumps(ident).encode()).hexdigest()[:32]

    @staticmethod
    def _is_complete(db: Path) -> bool:
        if not db.is_file():
            return False
        try:
            with closing(sqlite3.connect(_file_uri(db), uri=True)) as conn:
                row = conn.execute("SELECT value FROM meta WHERE key = 'complete'").fetchone()
        except sqlite3.Error:
            return False
        return bool(row and json.loads(row[0]))
