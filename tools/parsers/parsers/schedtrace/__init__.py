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

from . import _generated, codegen, schema
from .flatbuf import Decoder

FBS_DIR = Path(__file__).parent / "fbs"
_U32 = struct.Struct("<I")


@lru_cache(maxsize=1)
def decoder() -> Decoder:
    """The decoder of CellEvent buffers, from the schemas of fbs/."""
    return Decoder(schema.load(FBS_DIR / "cell_event.fbs"))


def schema_hash() -> str:
    """Hash of the schemas of fbs/ and of the generator of the decoder."""
    return codegen.source_hash()


@lru_cache(maxsize=1)
def _root() -> Callable[[bytes | memoryview], dict[str, Any]]:
    """The decoder of CellEvent buffers: _generated.root, or decoder().root, which is slower, if _generated.py is
    stale.
    """
    if _generated.SCHEMA_HASH == schema_hash():
        return _generated.root
    warnings.warn("parsers/schedtrace/_generated.py is stale, decoding without it. Regenerate it with "
                  "python -m parsers.schedtrace.codegen.", stacklevel=2)
    return decoder().root


def events(data: bytes | memoryview) -> Iterator[dict[str, Any]]:
    """The events of the contents of a schedtrace file, in order.

    Each has "timestamp_us" and "type", "CellStartEvent", "CellSlotEvent" or "CellStopEvent", with the fields of that
    event, e.g. "slot_tx", "latency_us", "inputs" and "decision" for a slot. An incomplete last event, e.g. of a
    trace still being written, is left out.
    """
    root = _root()
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


def event_at(data: bytes | memoryview, offset: int) -> dict[str, Any]:
    """The event at an offset of offsets(), as events() gives it."""
    size = _U32.unpack_from(data, offset)[0]
    event = _root()(memoryview(data)[offset + 4 : offset + 4 + size])
    value = event.pop("value") or {"type": None}
    return {**event, **value}


def read(path: str | os.PathLike[str]) -> Iterator[dict[str, Any]]:
    """The events of a schedtrace file, see events(), read one at a time, so that memory does not grow with the file."""
    root = _root()
    with open(path, "rb") as f:
        while len(prefix := f.read(4)) == 4:
            size = _U32.unpack(prefix)[0]
            buf = f.read(size)
            if len(buf) < size:
                return
            event = root(buf)
            value = event.pop("value") or {"type": None}
            yield {**event, **value}
