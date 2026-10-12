# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Scheduler event traces of OCUDU (schedtrace): the schedtrace_cell<N>.bin files that the scheduler event tracer
writes, one per cell: a header with the version of the file format, then size-prefixed FlatBuffers CellEvent buffers.

The schemas in fbs/ and the file format version in fbs/trace_file_format.h are copies of those of OCUDU; copy them again
and regenerate the decoder compiled from them, _generated.py, with python -m parsers.schedtrace.codegen --ocudu <dir>.
Traces of another major version, or without a header, are rejected. Fields that traces of a newer minor version append
are ignored.
"""

from __future__ import annotations

import os
import re
import struct
import warnings
from collections.abc import Callable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import _generated, schema
from .flatbuf import Decoder

FBS_DIR = Path(__file__).parent / "fbs"
# Magic bytes at the start of a trace, before its major and minor version.
MAGIC = b"SCHT"
HEADER = struct.Struct("<4sHH")
_U32 = struct.Struct("<I")


class FormatError(ValueError):
    """A trace without a header or of a file format version that the decoder does not support."""


def _format_version() -> tuple[int, int]:
    text = (FBS_DIR / "trace_file_format.h").read_text()
    major, minor = (re.search(rf"trace_file_version_{part}\s*=\s*(\d+);", text) for part in ("major", "minor"))
    return int(major.group(1)), int(minor.group(1))


# File format version of the schemas of fbs/, as (major, minor).
FORMAT_VERSION = _format_version()


def version(data: bytes | memoryview) -> tuple[int, int] | None:
    """The file format version in the header of the contents of a trace, or None without a header."""
    if len(data) < HEADER.size:
        return None
    magic, major, minor = HEADER.unpack_from(data, 0)
    return (major, minor) if magic == MAGIC else None


def check_version(found: tuple[int, int] | None, name: str | None = None) -> None:
    """Raises FormatError unless the decoder supports a file format version of version(); warns about a newer minor.
    Messages start with name if given.
    """
    prefix = f"{name}: " if name else ""
    if found is None:
        raise FormatError(f"{prefix}not a schedtrace file of format {_text(FORMAT_VERSION)} or later, its header is "
                          "missing. Traces written before OCUDU versioned the format are not supported.")
    if found[0] != FORMAT_VERSION[0]:
        raise FormatError(f"{prefix}schedtrace format {_text(found)} is not supported, only {FORMAT_VERSION[0]}.x. "
                          "Update fbs/ of parsers.schedtrace from the OCUDU that wrote it.")
    if found[1] > FORMAT_VERSION[1]:
        warnings.warn(f"{prefix}schedtrace format {_text(found)} is newer than {_text(FORMAT_VERSION)} of the decoder, so "
                      "the fields it adds are left out.")


def first_offset(data: bytes | memoryview, name: str | None = None) -> int:
    """The offset of the first event of the contents of a trace, after its header, checked with check_version()."""
    if not _partial_header(data):
        check_version(version(data), name)
    return HEADER.size


def _partial_header(head: bytes | memoryview) -> bool:
    """Whether the start of a trace is shorter than a header but could begin one, as in a trace just opened."""
    return len(head) < HEADER.size and MAGIC.startswith(bytes(head[: len(MAGIC)]))


def _text(v: tuple[int, int]) -> str:
    return f"{v[0]}.{v[1]}"


@lru_cache(maxsize=1)
def decoder() -> Decoder:
    """The decoder of CellEvent buffers, from the schemas of fbs/."""
    return Decoder(schema.load(FBS_DIR / "cell_event.fbs"))


def schema_hash() -> str:
    """Hash of the schemas and the file format version of fbs/ and of the generator of the decoders."""
    return _generated.SCHEMA_HASH


def _root(grid_only: bool) -> Callable[[bytes | memoryview], dict[str, Any]]:
    """The decoder of CellEvent buffers of _generated.py."""
    return _generated.root_grid if grid_only else _generated.root


def events(data: bytes | memoryview, grid_only: bool = False) -> Iterator[dict[str, Any]]:
    """The events of the contents of a schedtrace file, in order.

    Each has "timestamp_us" and "type", "CellStartEvent", "CellSlotEvent" or "CellStopEvent", with the fields of that
    event, e.g. "slot_tx", "latency_us", "inputs" and "decision" for a slot. An incomplete last event, e.g. of a
    trace still being written, is left out. grid_only leaves out the fields that grid.allocations() does not need,
    except the slot, latency and input types, which is faster; some may be left anyway.
    """
    root = _root(grid_only)
    view = memoryview(data)
    pos = first_offset(view)
    while pos + 4 <= len(view):
        size = _U32.unpack_from(view, pos)[0]
        if pos + 4 + size > len(view):
            return
        event = root(view[pos + 4 : pos + 4 + size])
        value = event.pop("value") or {"type": None}
        yield {**event, **value}
        pos += 4 + size


def offsets(data: bytes | memoryview, start: int | None = None, end: int | None = None) -> list[int]:
    """The offsets of the complete events of the contents of a trace from start, which must be the offset of an event,
    or the first one, up to end.
    """
    end = len(data) if end is None else end
    out = []
    pos = first_offset(data) if start is None else start
    while pos + 4 <= end:
        size = _U32.unpack_from(data, pos)[0]
        if pos + 4 + size > end:
            break
        out.append(pos)
        pos += 4 + size
    return out


def event_at(data: bytes | memoryview, offset: int, grid_only: bool = False) -> dict[str, Any]:
    """The event at an offset of offsets(), as events() gives it."""
    size = _U32.unpack_from(data, offset)[0]
    event = _root(grid_only)(memoryview(data)[offset + 4 : offset + 4 + size])
    value = event.pop("value") or {"type": None}
    return {**event, **value}


def read(path: str | os.PathLike[str], grid_only: bool = False) -> Iterator[dict[str, Any]]:
    """The events of a schedtrace file, see events(), read one at a time, so that memory does not grow with the file."""
    root = _root(grid_only)
    with open(path, "rb") as f:
        if _partial_header(head := f.read(HEADER.size)):
            return
        check_version(version(head), os.fspath(path))
        while len(prefix := f.read(4)) == 4:
            size = _U32.unpack(prefix)[0]
            buf = f.read(size)
            if len(buf) < size:
                return
            event = root(buf)
            value = event.pop("value") or {"type": None}
            yield {**event, **value}
