# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Command line entry point: parse sources, serve them and open the browser."""

from __future__ import annotations

import argparse
import socket
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path

from . import parallel
from .registry import SourceRegistry
from .sources.log_metrics import LogMetricsSource
from .store import StoreCache, default_cache_dir

SOURCE_TYPES = [LogMetricsSource()]


def _progress(name: str):
    def report(done: int, total: int) -> None:
        pct = 100 * done // total if total else 100
        print(f"\rParsing {name}: {pct:3d}%", end="" if done < total else "\n", file=sys.stderr, flush=True)

    return report


def _free_port(host: str, preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            # Same as the server socket, so that connections closing from a previous run do not count as busy.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise OSError("No free port.")


def _default_roots() -> list[Path]:
    """The home directory and the temp directory, where gnb logs are often written."""
    roots = [Path.home().resolve()]
    tmp = Path(tempfile.gettempdir()).resolve()
    if not tmp.is_relative_to(roots[0]):
        roots.append(tmp)
    return roots


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="ocudu-viz", description="Browser-based visualizer for OCUDU artifacts.")
    p.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Artifacts to open, each in its own tab: files, e.g. gnb.log, or directories of gNB artifacts. More can be "
        "opened from the page.",
    )
    p.add_argument("--host", default="127.0.0.1", help="Address to serve on (default: %(default)s).")
    p.add_argument("--port", type=int, default=8765, help="Port to serve on, or a free one if busy (default: %(default)s).")
    p.add_argument("--no-browser", action="store_true", help="Do not open the browser.")
    p.add_argument("--cache-dir", type=Path, help=f"Directory of parse caches (default: {default_cache_dir()}).")
    p.add_argument("--cache-size", type=float, default=2.0, help="Cache size limit in GB (default: %(default)s).")
    p.add_argument("--no-cache", action="store_true", help="Keep parsed data in memory only.")
    p.add_argument("--clear-cache", action="store_true", help="Remove all parse caches before starting.")
    p.add_argument(
        "-j",
        "--jobs",
        type=int,
        metavar="K",
        help="Worker processes that parse large logs, 1 to parse in the server process (default: one per CPU, up to "
        f"{parallel.MAX_WORKERS}). Logs under 8 MB are always parsed in the server process.",
    )
    p.add_argument(
        "--root",
        action="append",
        type=Path,
        default=[],
        help="Directory whose files can be opened from the page. Repeatable (default: the home and temp directories).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    cache = StoreCache(args.cache_dir, int(args.cache_size * (1 << 30)), enabled=not args.no_cache)
    if args.clear_cache:
        cache.clear()
    roots = [r.resolve() for r in args.root] or _default_roots()
    for r in roots:
        if not r.is_dir():
            print(f"ocudu-viz: {r}: not a directory.", file=sys.stderr)
            return 2
    if args.jobs is not None and args.jobs < 1:
        print("ocudu-viz: --jobs must be at least 1.", file=sys.stderr)
        return 2
    parallel.configure(args.jobs)
    parallel.warm_up()
    registry = SourceRegistry(cache, SOURCE_TYPES, roots)

    for path in args.files:
        is_dir = path.is_dir()
        if is_dir:
            files = registry.supported_files(path)
            if not files:
                print(f"ocudu-viz: {path}: no supported files in the directory.", file=sys.stderr)
                return 2
        elif path.is_file():
            files = [path]
        else:
            print(f"ocudu-viz: {path}: not a file or directory.", file=sys.stderr)
            return 2
        source_ids = []
        for f in files:
            source_type = next((st for st in SOURCE_TYPES if st.accepts(f)), None)
            if source_type is None:
                print(f"ocudu-viz: {f}: unsupported file type.", file=sys.stderr)
                return 2
            store = cache.open(f.resolve(), source_type, _progress(f.name))
            source_ids.append(registry.add_store(store, source_type).id)
        registry.add_run(path.resolve(), is_dir, source_ids)

    # Imported late so that --help and argument errors do not pay for the web stack.
    import uvicorn

    from .server import create_app

    port = _free_port(args.host, args.port)
    # Listening on all interfaces, e.g. inside a container, still serves the loopback address.
    url_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{url_host}:{port}/"
    nof_runs = len(registry.runs())
    print(f"Serving {nof_runs} run(s) at {url}, more can be opened from the page (Ctrl+C to stop)", file=sys.stderr)
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    # The pool is shut down with the server: on SIGTERM, uvicorn exits through the default handler, skipping atexit.
    uvicorn.run(create_app(registry, on_shutdown=parallel.shutdown), host=args.host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
