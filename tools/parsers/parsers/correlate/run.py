# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""UE contexts of the artifacts of a run, read from the files, and the UEs they combine into, see ues.combine()."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from ..log import events
from ..pcap import capture
from ..pcap.contexts import ContextTracker
from ..pcap.tshark import Tshark
from .ues import Context, Ue, combine


def log_contexts(path: str | os.PathLike[str], source: str | None = None) -> list[Context]:
    """The UE contexts of an OCUDU log, as events.UeTracker assigns its events, with their DU UE index and RNTI.

    source names the log in the contexts, by default its file name.
    """
    source = source or Path(path).name
    tracker = events.UeTracker()
    with open(path, encoding="utf-8", errors="replace") as f:
        for _, ev in events.iter_events(f):
            tracker.assign(ev)
    return [
        Context(source, lane.id, _epoch(lane.t_start), _epoch(lane.t_end or lane.t_start),
                {"ue": lane.du_ue, "rnti": lane.rnti}, lane.created and not lane.deleted)
        for lane in tracker.lanes
    ]


def pcap_contexts(tshark: Tshark, path: str | os.PathLike[str], source: str | None = None) -> list[Context]:
    """The UE contexts of an NGAP, F1AP or E1AP pcap, with their protocol UE identifiers and, for F1AP, C-RNTI.

    source names the pcap in the contexts, by default its file name. Other pcaps have none.
    """
    source = source or Path(path).name
    cap = capture.read(tshark, path)
    if cap.proto not in ("ngap", "f1ap", "e1ap"):
        return []
    tracker = ContextTracker(cap.proto)
    for msg in cap.messages:
        tracker.assign(msg)
    return [
        Context(source, ctx.id, ctx.t_start, ctx.t_end, {**ctx.ids, "rnti": ctx.rnti}, not ctx.released)
        for ctx in tracker.contexts
    ]


def run_ues(tshark: Tshark, f1ap: str | os.PathLike[str] | None = None,
            logs: list[str | os.PathLike[str]] | tuple = ()) -> list[Ue]:
    """The UEs of a run from its F1AP pcap, the most reliable source, then its logs, see ues.combine()."""
    sources = [pcap_contexts(tshark, f1ap)] if f1ap else []
    sources += [log_contexts(log) for log in logs]
    return combine(*sources)


def _epoch(t: datetime) -> float:
    # Log timestamps are UTC.
    return t.replace(tzinfo=timezone.utc).timestamp()
