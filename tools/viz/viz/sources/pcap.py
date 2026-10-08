# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Source type of the pcaps of an OCUDU run: NGAP, F1AP, E1AP, MAC-NR and RLC-NR captures, decoded by tshark."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parsers.pcap import f1ap, frames, messages, run
from parsers.ran.rnti import normalize as normalize_rnti
from parsers.pcap.tshark import Tshark

from .base import DatasetWriter, EventWriter, ProgressFn, RunIdentity
from .log_metrics import _parsers_version

# Protocol of a pcap by the dissector of its first frame.
_PROTOCOLS = {"ngap": "ngap", "f1ap": "f1ap", "e1ap": "e1ap", "mac-nr": "mac", "rlc-nr": "rlc"}
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
    version = f"2+parsers-{_parsers_version()}"

    def __init__(self, work_dir: str | os.PathLike[str] | None = None):
        """work_dir holds the pcaps staged for tshark, see parsers.pcap.tshark."""
        # The parse cache of viz keeps the results, so tshark extractions are not cached.
        self._tshark = Tshark(work_dir, cache=False)

    def accepts(self, path: Path) -> bool:
        return frames.is_pcap(path) and shutil.which("tshark") is not None

    def parse(self, path: Path, writer: DatasetWriter, progress: ProgressFn | None = None) -> None:
        proto = self._protocol(path)
        summaries = frames.summaries(self._tshark, path)
        for s in summaries:
            writer.add_record_text(s["frame"], f"{_iso(s['epoch'])} [{s['protocol']:<8}] {s['info']}")
        if summaries:
            writer.set_time_range(min(s["epoch"] for s in summaries), max(s["epoch"] for s in summaries))
        lengths = {s["frame"]: s["len"] for s in summaries}

        if proto in ("mac", "rlc"):
            for pdu in frames.pdus(self._tshark, path, proto):
                values = {k: v for k, v in pdu.items() if k not in ("frame", "epoch")}
                writer.add_row("pdus", pdu["frame"], pdu["epoch"], values)
            context = [label for label, _ in frames.PDU_FIELDS[proto]]
            writer.set_dataset_info("pdus", {"len": "bytes"}, context, label=f"{proto.upper()} PDUs")
        else:
            rrc = {m["frame"]: m for m in f1ap.messages(self._tshark, path)} if proto == "f1ap" else {}
            for msg in messages.messages(self._tshark, path, proto):
                values = {k: v for k, v in msg.items() if k not in ("frame", "epoch", "code")}
                values["len"] = lengths.get(msg["frame"])
                if proto == "f1ap":
                    detail = rrc.get(msg["frame"], {})
                    values.update(rrc=detail.get("rrc"), nas=detail.get("nas"), c_rnti=normalize_rnti(detail.get("crnti")))
                writer.add_row("messages", msg["frame"], msg["epoch"], values)
            context = ["procedure", "outcome", *(label for label, _ in messages.UE_ID_FIELDS[proto])]
            writer.set_dataset_info("messages", {"len": "bytes"}, context, label=f"{proto.upper()} messages")
        if progress:
            size = path.stat().st_size
            progress(size, size)

    def parse_events(self, path: Path, writer: EventWriter) -> None:
        proto = self._protocol(path)
        if proto not in _RELEASE_CODES:
            return
        crntis = {}
        rrc = {}
        if proto == "f1ap":
            for m in f1ap.messages(self._tshark, path):
                rrc[m["frame"]] = m["rrc"]
                if m["crnti"]:
                    crntis[m["frame"]] = normalize_rnti(m["crnti"])
        id_labels = [label for label, _ in messages.UE_ID_FIELDS[proto]]
        # Lane of each UE identifier in use, by label and value, and the identifiers and RNTI of each lane.
        lane_of: dict[tuple[str, str], int] = {}
        lanes: list[dict[str, Any]] = []
        for msg in messages.messages(self._tshark, path, proto):
            ids = {label: msg[label] for label in id_labels if msg[label]}
            lane = next((lane_of[(k, v)] for k, v in ids.items() if (k, v) in lane_of), None)
            if lane is None and ids:
                lane = len(lanes)
                lanes.append({"ids": {}, "rnti": None})
            if lane is not None:
                for k, v in ids.items():
                    lane_of[(k, v)] = lane
                    lanes[lane]["ids"].setdefault(k, v)
                if msg["frame"] in crntis:
                    lanes[lane]["rnti"] = lanes[lane]["rnti"] or crntis[msg["frame"]]
            rrc_type = rrc.get(msg["frame"])
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

    def _protocol(self, path: Path) -> str:
        check = run.check_pcap(self._tshark, path)
        proto = _PROTOCOLS.get(check.get("dissector", ""))
        if not check["ok"] or proto is None:
            raise ValueError(check.get("reason") or f"unsupported pcap, frame.protocols={check.get('frame_protocols')}")
        return proto


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
