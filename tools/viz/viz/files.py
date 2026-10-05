# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Directory listing restricted to a set of allowed root directories."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Entries returned for one directory.
MAX_ENTRIES = 5000


class PathNotAllowed(ValueError):
    """A path outside the allowed roots, or one that does not exist."""


def resolve_within(path: str | Path, roots: list[Path]) -> Path:
    """Resolves a path, following symlinks, and checks that it lies within one of the roots."""
    p = Path(path)
    if not p.is_absolute():
        raise PathNotAllowed(f"{path}: not an absolute path.")
    try:
        resolved = p.resolve(strict=True)
    except (OSError, RuntimeError):
        raise PathNotAllowed(f"{path}: does not exist.") from None
    if not any(resolved.is_relative_to(r.resolve()) for r in roots):
        raise PathNotAllowed(f"{path}: outside the allowed directories.")
    return resolved


def list_dir(path: str | Path, roots: list[Path], show_hidden: bool = False) -> dict[str, Any]:
    """Lists a directory within the roots: subdirectories first, then files, each sorted by name."""
    d = resolve_within(path, roots)
    if not d.is_dir():
        raise PathNotAllowed(f"{path}: not a directory.")
    entries = []
    try:
        children = list(d.iterdir())
    except PermissionError:
        raise PathNotAllowed(f"{path}: permission denied.") from None
    for child in children:
        if not show_hidden and child.name.startswith("."):
            continue
        try:
            st = child.stat()
            is_dir = child.is_dir()
        except OSError:
            continue
        entries.append({"name": child.name, "type": "dir" if is_dir else "file", "size": None if is_dir else st.st_size, "mtime": st.st_mtime})
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
    parent = d.parent
    in_roots = any(parent.is_relative_to(r.resolve()) for r in roots) and parent != d
    return {
        "path": str(d),
        "parent": str(parent) if in_roots else None,
        "entries": entries[:MAX_ENTRIES],
        "truncated": len(entries) > MAX_ENTRIES,
    }
