# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""HTTP API over the source stores, and the static frontend."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.types import Scope

from .files import PathNotAllowed, list_dir
from .registry import OpenError, SourceEntry, SourceRegistry
from .store import QueryError, Store

# Built frontend, produced by "npm run build" in the frontend directory.
STATIC_DIR = Path(__file__).parent / "static"
_NOT_BUILT_PAGE = (
    "<!doctype html><title>ocudu-viz</title><p>The ocudu-viz frontend is not built. Run the ocudu-viz "
    "wrapper script, which builds it in the container image, or run <code>npm ci && npm run build</code> in "
    "<code>tools/viz/frontend</code>.</p>"
)
# Rows per CSV chunk sent to the client.
_CSV_CHUNK_ROWS = 5000


def _utc_iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _csv_name(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in text)


def display_names(paths: list[Path]) -> list[str]:
    """File names, prefixed by the first differing directory when several sources share a name."""
    names = []
    for path in paths:
        twins = [p for p in paths if p.name == path.name and p != path]
        if not twins:
            names.append(path.name)
            continue
        parts = path.parent.parts
        idx = min(
            next((i for i, (a, b) in enumerate(zip(parts, t.parent.parts)) if a != b), min(len(parts), len(t.parent.parts)))
            for t in twins
        )
        if idx >= len(parts):
            names.append(str(path))
        elif idx == len(parts) - 1:
            names.append(f"{parts[idx]}/{path.name}")
        else:
            names.append(f"{parts[idx]}/\u2026/{path.name}")
    return names


class _RevalidatedStaticFiles(StaticFiles):
    """Static files that browsers revalidate on every load, so that frontend changes are never served stale."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _source_info(entry: SourceEntry, name: str) -> dict[str, Any]:
    info: dict[str, Any] = {
        "id": entry.id,
        "path": str(entry.path),
        "name": name,
        "status": entry.status,
        "progress": entry.progress,
        "error": entry.error,
        "t_min": None,
        "t_max": None,
        "datasets": [],
        "events_status": entry.events_status,
        "notes": [],
        "event_counts": {},
    }
    s = entry.store
    if s is None:
        return info
    info["t_min"], info["t_max"] = s.meta.get("t_min"), s.meta.get("t_max")
    info["event_counts"] = s.event_counts
    info["notes"] = s.meta.get("notes") or []
    info["datasets"] = [
        {
            "name": ds["name"],
            "kind": ds["kind"],
            "fields": [{"name": f, "type": t, "unit": ds["units"].get(f)} for f, t in ds["fields"].items()],
            "context": ds["context"],
            "label": ds["label"],
            "instance": ds["instance"],
            "t_min": ds["t_min"],
            "t_max": ds["t_max"],
        }
        for ds in s.datasets.values()
    ]
    return info


class _OpenRequest(BaseModel):
    path: str


def create_app(sources: SourceRegistry | list[Store], static_dir: Path = STATIC_DIR) -> FastAPI:
    """Serves the sources of a registry, or a fixed list of stores, and the frontend in static_dir.

    Source ids are the positions of the sources in opening order.
    """
    if isinstance(sources, SourceRegistry):
        registry = sources
    else:
        registry = SourceRegistry()
        for store in sources:
            registry.add_store(store)
    app = FastAPI(title="ocudu-viz")

    def get_store(source: int) -> Store:
        try:
            store = registry.get_ready(source)
        except KeyError:
            raise HTTPException(404, f"Unknown source {source}.") from None
        if store is None:
            raise HTTPException(409, f"Source {source} is not parsed yet.")
        return store

    def sources_info() -> list[dict[str, Any]]:
        entries = registry.entries()
        names = display_names([e.path for e in entries])
        return [_source_info(e, names[i]) for i, e in enumerate(entries)]

    @app.get("/api/sources")
    def list_sources() -> list[dict[str, Any]]:
        return sources_info()

    @app.post("/api/sources")
    def open_source(req: _OpenRequest) -> dict[str, Any]:
        try:
            entry = registry.open(req.path)
        except (OpenError, PathNotAllowed) as e:
            raise HTTPException(400, str(e)) from None
        return sources_info()[entry.id]

    @app.delete("/api/sources/{source_id}")
    def close_source(source_id: int) -> dict[str, Any]:
        try:
            registry.close(source_id)
        except KeyError:
            raise HTTPException(404, f"Unknown source {source_id}.") from None
        return sources_info()[source_id]

    @app.get("/api/roots")
    def roots() -> dict[str, Any]:
        return {"roots": [str(r) for r in registry.roots], "can_open": registry.cache is not None}

    @app.get("/api/fs")
    def fs(path: str | None = None, hidden: bool = False) -> dict[str, Any]:
        if not registry.roots:
            raise HTTPException(400, "No directories are available to browse.")
        try:
            return list_dir(path or registry.roots[0], registry.roots, hidden)
        except PathNotAllowed as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/series")
    def series(
        source: int,
        dataset: str,
        field: str,
        t0: float | None = None,
        t1: float | None = None,
        width: int = Query(1000, ge=1, le=20000),
        split_by: str | None = None,
        split_values: list[str] | None = Query(None),
        filter_expr: str | None = Query(None, alias="filter"),
        instance: str | None = None,
    ) -> dict[str, Any]:
        try:
            return get_store(source).series(dataset, field, t0, t1, width, split_by, split_values, filter_expr, instance)
        except QueryError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/stats")
    def stats(
        source: int,
        dataset: str,
        field: str,
        t0: float | None = None,
        t1: float | None = None,
        split_by: str | None = None,
        split_values: list[str] | None = Query(None),
        filter_expr: str | None = Query(None, alias="filter"),
        instance: str | None = None,
    ) -> dict[str, Any]:
        try:
            return get_store(source).stats(dataset, field, t0, t1, split_by, split_values, filter_expr, instance)
        except QueryError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/histogram")
    def histogram(
        source: int,
        dataset: str,
        field: str,
        t0: float | None = None,
        t1: float | None = None,
        split_by: str | None = None,
        split_values: list[str] | None = Query(None),
        filter_expr: str | None = Query(None, alias="filter"),
        instance: str | None = None,
        bins: int = Query(50, ge=1, le=1000),
    ) -> dict[str, Any]:
        try:
            return get_store(source).histogram(dataset, field, t0, t1, split_by, split_values, filter_expr, instance, bins)
        except QueryError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/table")
    def table(
        source: int,
        dataset: str,
        t0: float | None = None,
        t1: float | None = None,
        filter_expr: str | None = Query(None, alias="filter"),
        instance: str | None = None,
        limit: int = Query(1000, ge=1, le=100_000),
    ) -> dict[str, Any]:
        store = get_store(source)
        try:
            columns = store.table_columns(dataset)
            total = store.count_table_rows(dataset, t0, t1, filter_expr, instance)
            rows = [list(r) for r in store.table_rows(dataset, t0, t1, filter_expr, instance, columns, limit)]
        except QueryError as e:
            raise HTTPException(400, str(e)) from None
        ds = store.datasets[dataset]
        fields = [{"name": c, "type": ds["fields"][c], "unit": ds["units"].get(c), "context": c in ds["context"]} for c in columns]
        return {"fields": fields, "total": total, "rows": rows}

    @app.get("/api/table.csv")
    def table_csv(
        source: int,
        dataset: str,
        t0: float | None = None,
        t1: float | None = None,
        filter_expr: str | None = Query(None, alias="filter"),
        instance: str | None = None,
        fields: list[str] | None = Query(None),
    ) -> StreamingResponse:
        store = get_store(source)
        try:
            columns = store.table_columns(dataset, fields)
            # Validates the query before the response starts, so errors get a proper status.
            store.count_table_rows(dataset, t0, t1, filter_expr, instance)
        except QueryError as e:
            raise HTTPException(400, str(e)) from None
        units = store.datasets[dataset]["units"]
        # Header names carry the unit, with "%" spelled out to stay a plain identifier.
        header = ["time_utc", "line"] + [f"{c}_{units[c].replace('%', 'pct')}" if c in units else c for c in columns]

        def generate() -> Iterator[str]:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(header)
            rows = store.table_rows(dataset, t0, t1, filter_expr, instance, columns, limit=None)
            for i, (t, rec, *values) in enumerate(rows, start=1):
                writer.writerow([_utc_iso(t), rec, *values])
                if i % _CSV_CHUNK_ROWS == 0:
                    yield buf.getvalue()
                    buf.seek(0)
                    buf.truncate()
            yield buf.getvalue()

        name_parts = [store.path.stem, dataset] + ([instance] if instance else [])
        filename = _csv_name("_".join(name_parts)) + ".csv"
        return StreamingResponse(
            generate(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    @app.get("/api/events")
    def events(
        source: int,
        t0: float | None = None,
        t1: float | None = None,
        categories: list[str] | None = Query(None),
        ue: int | None = None,
        limit: int = Query(5000, ge=1, le=50_000),
    ) -> dict[str, Any]:
        return get_store(source).events(t0, t1, categories, ue, limit)

    @app.get("/api/trace")
    def trace(
        source: int,
        t0: float | None = None,
        t1: float | None = None,
        max_lanes: int = Query(300, ge=1, le=5000),
        limit: int = Query(5000, ge=1, le=50_000),
    ) -> dict[str, Any]:
        return get_store(source).trace(t0, t1, max_lanes, limit)

    @app.get("/api/context")
    def context(source: int, dataset: str, field: str) -> list[Any]:
        try:
            return get_store(source).context_values(dataset, field)
        except QueryError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/records")
    def records(source: int, around: int = Query(..., ge=1), count: int = Query(50, ge=1, le=1000)) -> list[dict[str, Any]]:
        return get_store(source).records(around, count)

    if (static_dir / "index.html").is_file():
        app.mount("/", _RevalidatedStaticFiles(directory=static_dir, html=True), name="static")
    else:

        @app.get("/", response_class=HTMLResponse)
        def not_built() -> str:
            return _NOT_BUILT_PAGE

    return app
