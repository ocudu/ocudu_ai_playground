# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Scheduler event traces of OCUDU (schedtrace): the schedtrace_cell<N>.bin files that the scheduler event tracer
writes, one per cell, of size-prefixed FlatBuffers CellEvent buffers.

The schemas in fbs/ are copies of lib/scheduler/trace/fbs of OCUDU; copy them again when OCUDU changes them, then
regenerate the decoder compiled from them, _generated.py, with python -m parsers.schedtrace.codegen. Fields that newer
traces append are ignored.
"""

from __future__ import annotations

import os
import struct
import warnings
from collections.abc import Callable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import _generated, schema
from .flatbuf import Decoder

FBS_DIR = Path(__file__).parent / "fbs"
_U32 = struct.Struct("<I")


@lru_cache(maxsize=1)
def decoder() -> Decoder:
    """The decoder of CellEvent buffers, from the schemas of fbs/."""
    return Decoder(schema.load(FBS_DIR / "cell_event.fbs"))


def schema_hash() -> str:
    """Hash of the schemas of fbs/ and of the generator of the decoders."""
    # Imported here so that running codegen as a module does not find it already imported.
    from . import codegen

    return codegen.source_hash()


@lru_cache(maxsize=1)
def _stale() -> bool:
    """Whether _generated.py is stale, which it warns about."""
    if _generated.SCHEMA_HASH == schema_hash():
        return False
    warnings.warn("parsers/schedtrace/_generated.py is stale, decoding without it. Regenerate it with "
                  "python -m parsers.schedtrace.codegen.", stacklevel=3)
    return True


def _root(grid_only: bool) -> Callable[[bytes | memoryview], dict[str, Any]]:
    """The decoder of CellEvent buffers of _generated.py, or decoder().root, which is slower, if it is stale."""
    if _stale():
        return decoder().root
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
    pos = 0
    while pos + 4 <= len(view):
        size = _U32.unpack_from(view, pos)[0]
        if pos + 4 + size > len(view):
            return
        event = root(view[pos + 4 : pos + 4 + size])
        value = event.pop("value") or {"type": None}
        yield {**event, **value}
        pos += 4 + size


def offsets(data: bytes | memoryview, start: int = 0, end: int | None = None) -> list[int]:
    """The offsets of the complete events of data from start, which must be the offset of an event, up to end."""
    end = len(data) if end is None else end
    out = []
    pos = start
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
        while len(prefix := f.read(4)) == 4:
            size = _U32.unpack(prefix)[0]
            buf = f.read(size)
            if len(buf) < size:
                return
            event = root(buf)
            value = event.pop("value") or {"type": None}
            yield {**event, **value}
