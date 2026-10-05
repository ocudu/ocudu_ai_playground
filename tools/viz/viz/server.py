# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""HTTP API over the source stores, and the static frontend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .store import QueryError, Store

# Built frontend, produced by "npm run build" in the frontend directory.
STATIC_DIR = Path(__file__).parent / "static"
_NOT_BUILT_PAGE = (
    "<!doctype html><title>ocudu-viz</title><p>The ocudu-viz frontend is not built. Run the ocudu-viz "
    "wrapper script, which builds it in the container image, or run <code>npm ci && npm run build</code> in "
    "<code>tools/viz/frontend</code>.</p>"
)


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


def create_app(stores: list[Store], static_dir: Path = STATIC_DIR) -> FastAPI:
    """Serves the given sources and the frontend in static_dir. Source ids are their positions in stores."""
    app = FastAPI(title="ocudu-viz")

    def get_store(source: int) -> Store:
        if not 0 <= source < len(stores):
            raise HTTPException(404, f"Unknown source {source}.")
        return stores[source]

    names = display_names([s.path for s in stores])

    @app.get("/api/sources")
    def sources() -> list[dict[str, Any]]:
        return [
            {
                "id": i,
                "path": str(s.path),
                "name": names[i],
                "t_min": s.meta.get("t_min"),
                "t_max": s.meta.get("t_max"),
                "datasets": [
                    {
                        "name": ds["name"],
                        "kind": ds["kind"],
                        "fields": [
                            {"name": f, "type": t, "unit": ds["units"].get(f)} for f, t in ds["fields"].items()
                        ],
                        "context": ds["context"],
                    }
                    for ds in s.datasets.values()
                ],
            }
            for i, s in enumerate(stores)
        ]

    @app.get("/api/series")
    def series(
        source: int,
        dataset: str,
        field: str,
        t0: float | None = None,
        t1: float | None = None,
        width: int = Query(1000, ge=1, le=20000),
        group_by: str | None = None,
        groups: list[str] | None = Query(None),
        filter_expr: str | None = Query(None, alias="filter"),
    ) -> dict[str, Any]:
        try:
            return get_store(source).series(dataset, field, t0, t1, width, group_by, groups, filter_expr)
        except QueryError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/stats")
    def stats(
        source: int,
        dataset: str,
        field: str,
        t0: float | None = None,
        t1: float | None = None,
        group_by: str | None = None,
        groups: list[str] | None = Query(None),
        filter_expr: str | None = Query(None, alias="filter"),
    ) -> dict[str, Any]:
        try:
            return get_store(source).stats(dataset, field, t0, t1, group_by, groups, filter_expr)
        except QueryError as e:
            raise HTTPException(400, str(e)) from None

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
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    else:

        @app.get("/", response_class=HTMLResponse)
        def not_built() -> str:
            return _NOT_BUILT_PAGE

    return app
