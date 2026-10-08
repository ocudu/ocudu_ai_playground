# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Summaries of OCUDU pcaps: packets, time span, UE identifiers, procedure counts and failures."""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any

from .names import epoch_to_iso
from .tshark import Tshark, TsharkError

logger = logging.getLogger("parsers")

# Per protocol, the procedure code field, the UE identifier fields by label, and the filter of failed procedures.
PROTO_FIELDS: dict[str, dict[str, Any]] = {
    "ngap": {
        "proc": ["ngap.procedureCode"],
        "ue": [("ran", "ngap.RAN_UE_NGAP_ID"), ("amf", "ngap.AMF_UE_NGAP_ID")],
        # Only unsuccessful outcomes, since successful messages also carry a cause, e.g. UEContextReleaseCommand.
        "failure_filter": "ngap.unsuccessfulOutcome_element",
    },
    "f1ap": {
        "proc": ["f1ap.procedureCode"],
        "ue": [("du", "f1ap.GNB_DU_UE_F1AP_ID"), ("cu", "f1ap.GNB_CU_UE_F1AP_ID")],
        "failure_filter": "f1ap.unsuccessfulOutcome_element",
    },
    "e1ap": {
        "proc": ["e1ap.procedureCode"],
        "ue": [("cp", "e1ap.GNB_CU_CP_UE_E1AP_ID"), ("up", "e1ap.GNB_CU_UP_UE_E1AP_ID")],
        "failure_filter": "e1ap.unsuccessfulOutcome_element",
    },
    "mac": {"proc": [], "ue": [("rnti", "mac-nr.rnti")], "failure_filter": None},
    "rlc": {"proc": [], "ue": [("ueid", "rlc-nr.ueid")], "failure_filter": None},
}


def summarise(tshark: Tshark, pcap: Path, *, top: int = 5) -> dict[str, Any]:
    """Summary of a pcap, whose protocol is its file stem, e.g. "ngap".

    Returns "file", "proto" and "packets", and once there are packets, the time span ("first_epoch", "last_epoch",
    "duration_s", "first_iso", "last_iso"), the distinct UE identifiers by label, the top procedure codes and the
    number of failures, for the protocols that have them.
    """
    proto = pcap.stem
    spec = PROTO_FIELDS.get(proto)
    out: dict[str, Any] = {"file": str(pcap), "proto": proto}
    fields = ["frame.time_epoch"]
    if spec:
        fields += spec["proc"] + [f for _, f in spec["ue"]]

    rows = list(tshark.iter_fields(pcap, fields, tag=f"overview-{proto}-v3"))
    out["packets"] = len(rows)
    if not rows:
        out["empty"] = True
        return out

    epochs = [float(r[0]) for r in rows if r[0]]
    if epochs:
        out["first_epoch"] = min(epochs)
        out["last_epoch"] = max(epochs)
        out["duration_s"] = out["last_epoch"] - out["first_epoch"]
        out["first_iso"] = epoch_to_iso(out["first_epoch"])
        out["last_iso"] = epoch_to_iso(out["last_epoch"])

    if spec and spec["proc"]:
        out["top_procedures"] = Counter(r[1] for r in rows if r[1]).most_common(top)
    if spec:
        ue_start = 1 + len(spec["proc"])
        # Per label, so that one NGAP UE with both a RAN and an AMF identifier does not count as two.
        per_label: dict[str, set[str]] = {label: set() for label, _ in spec["ue"]}
        for r in rows:
            for (label, _), val in zip(spec["ue"], r[ue_start:ue_start + len(spec["ue"])]):
                if val:
                    per_label[label].add(val)
        out["distinct_ues_by_label"] = {k: sorted(v) for k, v in per_label.items()}
        if spec["failure_filter"]:
            try:
                fail_lines = tshark.run(
                    ["-r", str(tshark.stage(pcap)), "-Y", spec["failure_filter"], "-T", "fields", "-e", "frame.number"]
                )
                out["failures"] = len(fail_lines)
            except TsharkError as e:
                logger.warning("failure-count tshark call failed for %s: %s", pcap, e)
                out["failures"] = None
    return out


def proc_code_counts(
    tshark: Tshark,
    pcap: Path,
    proto: str,
    *,
    initiating_only: bool = False,
    time_range: tuple[float, float] | None = None,
) -> Counter[str]:
    """Count of each procedureCode in an ngap, f1ap or e1ap pcap.

    initiating_only counts only initiating messages, and time_range only frames in [start, end) epochs.
    """
    filters: list[str] = []
    if initiating_only:
        filters.append(f"{proto}.initiatingMessage_element")
    if time_range is not None:
        a, b = time_range
        filters.append(f"frame.time_epoch >= {a} && frame.time_epoch < {b}")
    display_filter = " && ".join(f"({f})" for f in filters) if filters else None
    range_tag = f"{time_range[0]},{time_range[1]}" if time_range else ""
    tag = f"proc-codes-{proto}-{int(initiating_only)}-{range_tag}"
    counts: Counter[str] = Counter()
    for _, code in tshark.iter_fields(pcap, ["frame.time_epoch", f"{proto}.procedureCode"], display_filter=display_filter, tag=tag):
        if code:
            counts[code] += 1
    return counts
