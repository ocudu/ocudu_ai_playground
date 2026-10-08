# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Source type of the pcaps of an OCUDU run: NGAP, F1AP, E1AP, MAC-NR and RLC-NR captures, decoded by tshark."""

from __future__ import annotations

import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parsers.pcap import capture, frames, messages
from parsers.pcap.tshark import Tshark
from parsers.ran.rnti import normalize as normalize_rnti

from .base import DatasetWriter, EventWriter, ProgressFn, RunIdentity
from .log_metrics import _parsers_version

# Procedure code that releases the UE context of each protocol, whose response ends the lane of its UE.
_RELEASE_CODES = {"ngap": "41", "f1ap": "6", "e1ap": "11"}
# Labels of the UE identifiers shown in the trace, by identifier label.
_ID_LABELS = {
    "ran_ue_ngap_id": "ran_ngap",
    "amf_ue_ngap_id": "amf_ngap",
    "du_ue_f1ap_id": "du_f1ap",
    "cu_ue_f1ap_id": "cu_f1ap",
    "cu_cp_ue_e1ap_id": "cu_cp_e1ap",
    "cu_up_ue_e1ap_id": "cu_up_e1ap",
}


class PcapSource:
    """One dataset of the messages or PDUs of a pcap, and the events of its NGAP, F1AP or E1AP messages. Records are
    frames, identified by frame number, with their tshark summary as text.
    """

    name = "pcap"
    version = f"3+parsers-{_parsers_version()}"

    def __init__(self, work_dir: str | os.PathLike[str] | None = None):
        """work_dir holds the pcaps staged for tshark, see parsers.pcap.tshark."""
        # The parse cache of viz keeps the results, so tshark extractions are not cached.
        self._tshark = Tshark(work_dir, cache=False)
        # Pcaps read by parse() for parse_events(), which follows it, by path. Sources parse in their own threads.
        self._captures: dict[Path, capture.Capture] = {}
        self._lock = threading.Lock()

    def accepts(self, path: Path) -> bool:
        return frames.is_pcap(path) and shutil.which("tshark") is not None

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
        if proto not in _RELEASE_CODES:
            return
        id_labels = [label for label, _ in messages.UE_ID_FIELDS[proto]]
        # Lane of each UE identifier in use, by label and value, and the identifiers and RNTI of each lane.
        lane_of: dict[tuple[str, str], int] = {}
        lanes: list[dict[str, Any]] = []
        for msg in cap.messages:
            ids = {label: msg[label] for label in id_labels if msg[label]}
            lane = next((lane_of[(k, v)] for k, v in ids.items() if (k, v) in lane_of), None)
            if lane is None and ids:
                lane = len(lanes)
                lanes.append({"ids": {}, "rnti": None})
            if lane is not None:
                for k, v in ids.items():
                    lane_of[(k, v)] = lane
                    lanes[lane]["ids"].setdefault(k, v)
                if msg.get("crnti"):
                    lanes[lane]["rnti"] = lanes[lane]["rnti"] or normalize_rnti(msg["crnti"])
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
                "lane": lane,
                "rnti": lanes[lane]["rnti"] if lane is not None else None,
            }
            writer.add_event(msg["frame"], msg["epoch"], event)
            # Identifiers are reused by later UEs once the context of their UE is released.
            if lane is not None and msg["code"] == _RELEASE_CODES[proto] and msg["outcome"] == "successful":
                for k, v in ids.items():
                    lane_of.pop((k, v), None)
        for i, lane in enumerate(lanes):
            label = " ".join(f"{_ID_LABELS[k]}={lane['ids'][k]}" for k in id_labels if k in lane["ids"])
            writer.add_lane(i, None, lane["rnti"], label)

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
