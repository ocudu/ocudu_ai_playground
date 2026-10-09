# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Scheduler event traces of OCUDU (schedtrace): the schedtrace_cell<N>.bin files that the scheduler event tracer
writes, one per cell, of size-prefixed FlatBuffers CellEvent buffers.

The schemas in fbs/ are copies of lib/scheduler/trace/fbs of OCUDU, which decoding needs; copy them again when OCUDU
changes them. Fields that newer traces append are ignored.
"""

from __future__ import annotations

import os
import struct
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import schema
from .flatbuf import Decoder

FBS_DIR = Path(__file__).parent / "fbs"
_U32 = struct.Struct("<I")


@lru_cache(maxsize=1)
def decoder() -> Decoder:
    """The decoder of CellEvent buffers, from the schemas of fbs/."""
    return Decoder(schema.load(FBS_DIR / "cell_event.fbs"))


def events(data: bytes | memoryview) -> Iterator[dict[str, Any]]:
    """The events of the contents of a schedtrace file, in order.

    Each has "timestamp_us" and "type", "CellStartEvent", "CellSlotEvent" or "CellStopEvent", with the fields of that
    event, e.g. "slot_tx", "latency_us", "inputs" and "decision" for a slot. An incomplete last event, e.g. of a
    trace still being written, is left out.
    """
    dec = decoder()
    view = memoryview(data)
    pos = 0
    while pos + 4 <= len(view):
        size = _U32.unpack_from(view, pos)[0]
        if pos + 4 + size > len(view):
            return
        event = dec.root(view[pos + 4 : pos + 4 + size])
        value = event.pop("value") or {"type": None}
        yield {**event, **value}
        pos += 4 + size


def read(path: str | os.PathLike[str]) -> Iterator[dict[str, Any]]:
    """The events of a schedtrace file, see events()."""
    yield from events(Path(path).read_bytes())
