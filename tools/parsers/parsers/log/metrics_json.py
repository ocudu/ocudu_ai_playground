# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""The metrics.json that OCUDU applications write, a JSON array of metric records, and a rollup of its scheduler cell
metrics: peaks, HARQ and allocation failures, Msg3 outcomes and events.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Cell metrics of the failed PDCCH allocations.
_FAILED_PDCCH_KEYS = ("failed_dl_pdcch", "failed_ul_pdcch", "failed_common_dl_pdcch", "failed_common_ul_pdcch")


@dataclass
class MetricsRollup:
    """Rollup of the cell metrics of the records of a metrics.json."""

    records: int = 0
    # Records with scheduler cell metrics, none for a metrics.json of another format, e.g. of srsRAN.
    cell_records: int = 0
    # Highest bitrate of any UE in any record, in bps.
    peak_dl_brate: float = 0.0
    peak_ul_brate: float = 0.0
    max_latency_us: float = 0.0
    late_dl_harqs: int = 0
    late_ul_harqs: int = 0
    # Failed DL and UL PDCCH allocations, of UEs and of common channels.
    failed_pdcch: int = 0
    failed_uci: int = 0
    # Error indications.
    errors: int = 0
    msg3_ok: int = 0
    msg3_nok: int = 0
    # Events of the event lists, by type.
    event_counts: Counter = field(default_factory=Counter)


def load_records(path: str | os.PathLike[str]) -> list[Any]:
    """The records of a metrics.json, or those of its complete lines when the array is malformed, e.g. unclosed by a
    run killed while writing it.
    """
    text = Path(path).read_text(errors="replace").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        pass
    records = []
    for line in text.lstrip("[").rstrip("]").splitlines():
        line = line.strip().rstrip(",")
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def rollup(records: Iterable[Any]) -> MetricsRollup:
    """The rollup of the cell metrics of metrics records."""
    out = MetricsRollup()
    for obj in records:
        out.records += 1
        cells = obj.get("cells") or []
        out.cell_records += bool(cells)
        for cell in cells:
            cm = cell.get("cell_metrics", {})
            out.late_dl_harqs += cm.get("late_dl_harqs", 0) or 0
            out.late_ul_harqs += cm.get("late_ul_harqs", 0) or 0
            out.failed_pdcch += sum(cm.get(k, 0) or 0 for k in _FAILED_PDCCH_KEYS)
            out.failed_uci += cm.get("nof_failed_uci_allocs", 0) or 0
            out.errors += cm.get("error_indication_count", 0) or 0
            out.msg3_ok += cm.get("msg3_nof_ok", 0) or 0
            out.msg3_nok += cm.get("msg3_nof_nok", 0) or 0
            for ue in cell.get("ue_list", []) or []:
                out.peak_dl_brate = max(out.peak_dl_brate, ue.get("dl_brate", 0) or 0)
                out.peak_ul_brate = max(out.peak_ul_brate, ue.get("ul_brate", 0) or 0)
            out.max_latency_us = max(out.max_latency_us, cm.get("max_latency", 0) or 0)
            for ev in cell.get("event_list", []) or []:
                if t := ev.get("event_type"):
                    out.event_counts[t] += 1
    return out
