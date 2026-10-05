# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Command line entry point: parse sources, serve them and open the browser."""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from .sources.log_metrics import LogMetricsSource
from .store import Store, StoreCache, default_cache_dir

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


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="ocudu-viz", description="Browser-based visualizer for OCUDU artifacts.")
    p.add_argument("files", nargs="*", type=Path, help="Artifacts to open, e.g. gnb.log du.log.")
    p.add_argument("--host", default="127.0.0.1", help="Address to serve on (default: %(default)s).")
    p.add_argument("--port", type=int, default=8765, help="Port to serve on, or a free one if busy (default: %(default)s).")
    p.add_argument("--no-browser", action="store_true", help="Do not open the browser.")
    p.add_argument("--cache-dir", type=Path, help=f"Directory of parse caches (default: {default_cache_dir()}).")
    p.add_argument("--cache-size", type=float, default=2.0, help="Cache size limit in GB (default: %(default)s).")
    p.add_argument("--no-cache", action="store_true", help="Keep parsed data in memory only.")
    p.add_argument("--clear-cache", action="store_true", help="Remove all parse caches before starting.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    cache = StoreCache(args.cache_dir, int(args.cache_size * (1 << 30)), enabled=not args.no_cache)
    if args.clear_cache:
        cache.clear()
        if not args.files:
            return 0
    if not args.files:
        print("ocudu-viz: no files given.", file=sys.stderr)
        return 2

    stores: list[Store] = []
    for path in args.files:
        if not path.is_file():
            print(f"ocudu-viz: {path}: not a file.", file=sys.stderr)
            return 2
        source_type = next((st for st in SOURCE_TYPES if st.accepts(path)), None)
        if source_type is None:
            print(f"ocudu-viz: {path}: unsupported file type.", file=sys.stderr)
            return 2
        stores.append(cache.open(path, source_type, _progress(path.name)))

    # Imported late so that --help and argument errors do not pay for the web stack.
    import uvicorn

    from .server import create_app

    port = _free_port(args.host, args.port)
    # Listening on all interfaces, e.g. inside a container, still serves the loopback address.
    url_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{url_host}:{port}/"
    print(f"Serving {len(stores)} source(s) at {url} (Ctrl+C to stop)", file=sys.stderr)
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    uvicorn.run(create_app(stores), host=args.host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
