# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Source type of the pcaps of an OCUDU run: NGAP, F1AP, E1AP, MAC-NR and RLC-NR captures, decoded by tshark."""

from __future__ import annotations

import os
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parsers.pcap import capture, contexts, frames, messages
from parsers.pcap.tshark import Tshark
from parsers.ran.rnti import normalize as normalize_rnti

from .base import DatasetWriter, EventWriter, ProgressFn, RunIdentity
from .log_metrics import _parsers_version

# Names of the MAC and RLC captures of a run, e.g. mac.pcap or du_rlc.pcap, which can be huge.
_ON_REQUEST_NAME_RE = re.compile(r"(?:^|[_.-])(?:mac|rlc)(?:[_.-]|$)", re.IGNORECASE)



class PcapSource:
    """One dataset of the messages or PDUs of a pcap, and the events of its NGAP, F1AP or E1AP messages. Records are
    frames, identified by frame number, with their tshark summary as text.
    """

    name = "pcap"
    version = f"5+parsers-{_parsers_version()}"

    def __init__(self, work_dir: str | os.PathLike[str] | None = None):
        """work_dir holds the pcaps staged for tshark, see parsers.pcap.tshark."""
        # The parse cache of viz keeps the results, so tshark extractions are not cached.
        self._tshark = Tshark(work_dir, cache=False)
        # Pcaps read by parse() for parse_events(), which follows it, by path. Sources parse in their own threads.
        self._captures: dict[Path, capture.Capture] = {}
        self._lock = threading.Lock()

    def accepts(self, path: Path) -> bool:
        return frames.is_pcap(path) and shutil.which("tshark") is not None

    def on_request(self, path: Path) -> bool:
        """Whether a pcap is a MAC or RLC capture, by its name, parsed only on request with the other files of its run."""
        return _ON_REQUEST_NAME_RE.search(path.stem) is not None

    def parse(self, path: Path, writer: DatasetWriter, progress: ProgressFn | None = None) -> None:
        cap = self._read(path)
        # Kept also for pcaps without events, so that parse_events() does not read them again to know.
        with self._lock:
            self._captures[path] = cap
        proto, summaries = cap.proto, cap.frames
        for s in summaries:
            writer.add_record_text(s["frame"], f"{_iso(s['epoch'])} [{s['protocol']:<8}] {s['info']}")
        if summaries:
            writer.set_time_range(min(s["epoch"] for s in summaries), max(s["epoch"] for s in summaries))
        lengths = {s["frame"]: s["len"] for s in summaries}

        if proto in ("mac", "rlc"):
            for pdu in cap.pdus:
                values = {k: v for k, v in pdu.items() if k not in ("frame", "epoch")}
                writer.add_row("pdus", pdu["frame"], pdu["epoch"], values)
            context = [label for label, _ in frames.PDU_FIELDS[proto]]
            writer.set_dataset_info("pdus", {"len": "bytes"}, context, label=f"{proto.upper()} PDUs")
        else:
            for msg in cap.messages:
                values = {k: v for k, v in msg.items() if k not in ("frame", "epoch", "code", "crnti")}
                values["len"] = lengths.get(msg["frame"])
                if proto == "f1ap":
                    values["c_rnti"] = normalize_rnti(msg["crnti"])
                writer.add_row("messages", msg["frame"], msg["epoch"], values)
            context = ["procedure", "outcome", *(label for label, _ in messages.UE_ID_FIELDS[proto])]
            writer.set_dataset_info("messages", {"len": "bytes"}, context, label=f"{proto.upper()} messages")
        if progress:
            size = path.stat().st_size
            progress(size, size)

    def parse_events(self, path: Path, writer: EventWriter) -> None:
        with self._lock:
            cap = self._captures.pop(path, None)
        # A pcap whose datasets were cached is not parsed again before its events.
        if cap is None:
            cap = self._read(path)
        proto = cap.proto
        if proto not in contexts.RELEASE_CODES:
            return
        tracker = contexts.ContextTracker(proto)
        for msg in cap.messages:
            ctx = tracker.assign(msg)
            rrc_type = msg.get("rrc")
            if msg["outcome"] == "unsuccessful":
                category = "failure"
            elif rrc_type:
                category = "rrc"
            else:
                category = proto
            text = msg["info"] + (f" (cause: {msg['cause']})" if msg["cause"] else "")
            event = {
                "type": rrc_type or msg["procedure"],
                "category": category,
                "layer": proto.upper(),
                "cause": msg["cause"],
                "text": text,
                "lane": ctx.id if ctx is not None else None,
                "rnti": ctx.rnti if ctx is not None else None,
            }
            writer.add_event(msg["frame"], msg["epoch"], event)
        for ctx in tracker.contexts:
            writer.add_lane(ctx.id, None, ctx.rnti, ctx.label(), links=ctx.links)

    def run_identity(self, path: Path) -> RunIdentity | None:
        span = frames.time_span(path)
        return RunIdentity(None, *span) if span else None

    def record_detail(self, path: Path, record: int) -> str:
        return frames.decode(self._tshark, path, record)

    def _read(self, path: Path) -> capture.Capture:
        cap = capture.read(self._tshark, path)
        if cap.proto is None:
            raise ValueError(f"unsupported pcap, frame.protocols={cap.frame_protocols or 'none'}")
        return cap


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
