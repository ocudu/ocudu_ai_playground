# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""F1AP pcaps: the UEs with their identifiers, and the messages with the RRC and NAS messages they carry."""

from __future__ import annotations

import os
from typing import Any

from ..ran.nas import nas_name
from ..ran.procedures import proc_name
from ..ran.rrc import RRC_MESSAGE_TYPES, decode_ccch_type
from .tshark import Tshark
from .values import epoch_to_iso, to_int

UE_ID_FIELDS = [
    "frame.number",
    "frame.time_epoch",
    "f1ap.procedureCode",
    "f1ap.GNB_DU_UE_F1AP_ID",
    "f1ap.GNB_CU_UE_F1AP_ID",
    "f1ap.C_RNTI",
]

MESSAGE_FIELDS = [
    "frame.number",
    "frame.time_epoch",
    "f1ap.procedureCode",
    "f1ap.GNB_DU_UE_F1AP_ID",
    "f1ap.GNB_CU_UE_F1AP_ID",
    "f1ap.C_RNTI",
    "f1ap.SRBID",
    "f1ap.RRCContainer",
    "nas_5gs.mm.message_type",
    "nas_5gs.sm.message_type",
]

# Procedures carrying an RRC container, and the downlink ones among them.
_RRC_PROCS = {5, 6, 7, 11, 12, 13}
_DL_PROCS = {5, 6, 7, 12}


def ue_ids(tshark: Tshark, pcap: str | os.PathLike[str], *, force: bool = False) -> list[dict[str, Any]]:
    """The UEs of an F1AP pcap in order of appearance, each with its first frame and message and its identifiers.

    A UE is identified by its gNB-CU-UE-F1AP-ID, or its gNB-DU-UE-F1AP-ID before the CU assigns one.
    """
    rows = []
    for frame, epoch, code, du_id, cu_id, crnti in tshark.iter_fields(pcap, UE_ID_FIELDS, tag="f1ap-ue-ids-v1", force=force):
        if epoch:
            rows.append({
                "frame": int(frame) if frame else None,
                "epoch": float(epoch),
                "code": code,
                "du_ue_id": du_id or None,
                "cu_ue_id": cu_id or None,
                "crnti": crnti or None,
            })
    clusters = sorted(_build_clusters(rows), key=lambda c: c["first_epoch"])
    return [
        {
            "frame": c["frame"],
            "first_iso": epoch_to_iso(c["first_epoch"]),
            "message": proc_name("f1ap", c["first_code"], with_code=False),
            "cu_ue_f1ap_id": c["cu_ue_f1ap_id"],
            "du_ue_f1ap_ids": sorted(c["du_ue_f1ap_ids"]),
            "crntis": sorted(c["crntis"]),
            "first_epoch": c["first_epoch"],
        }
        for c in clusters
    ]


def messages(tshark: Tshark, pcap: str | os.PathLike[str], *, force: bool = False) -> list[dict[str, Any]]:
    """The messages of an F1AP pcap in time order, with the RRC message and the NAS message they carry, if any."""
    rrc_types = valid_rrc_types(tshark, pcap)
    fields = MESSAGE_FIELDS + [_rrc_field(m) for m in rrc_types]
    n_scalar = len(MESSAGE_FIELDS)
    rows = []
    for r in tshark.iter_fields(pcap, fields, tag=f"f1ap-messages-v1-{len(fields)}", force=force):
        frame, epoch, code, du_id, cu_id, crnti, srbid, container, nas_mm, nas_sm = r[:n_scalar]
        if not epoch:
            continue
        row = {
            "frame": int(frame) if frame else None,
            "epoch": float(epoch),
            "code": code,
            "du_ue_id": du_id or None,
            "cu_ue_id": cu_id or None,
            "crnti": crnti or None,
            "srbid": srbid or None,
            "rrc_container": container or None,
            "rrc_elements": dict(zip(rrc_types, r[n_scalar:])),
        }
        row["rrc"] = resolve_rrc(row)
        row["nas"] = nas_name(nas_mm, nas_sm)
        rows.append(row)
    rows.sort(key=lambda x: x["epoch"])
    return [
        {
            "frame": x["frame"],
            "first_iso": epoch_to_iso(x["epoch"]),
            "message": proc_name("f1ap", x["code"], with_code=False),
            "rrc": x["rrc"],
            "nas": x["nas"],
            "cu_ue_f1ap_id": x["cu_ue_id"],
            "du_ue_f1ap_id": x["du_ue_id"],
            "crnti": x["crnti"],
        }
        for x in rows
    ]


def valid_rrc_types(tshark: Tshark, pcap: str | os.PathLike[str]) -> list[str]:
    """The RRC message types whose field this tshark build knows."""
    valid = set(tshark.valid_fields(pcap, [_rrc_field(m) for m in RRC_MESSAGE_TYPES]))
    return [m for m in RRC_MESSAGE_TYPES if _rrc_field(m) in valid]


def resolve_rrc(row: dict[str, Any]) -> str | None:
    """RRC message type of a message row: tshark's dissection, else decoded or inferred from the container."""
    for name, val in row["rrc_elements"].items():
        if val:
            return name
    # tshark does not dissect the container of a UEContextReleaseCommand.
    if not row["rrc_container"]:
        return None
    code = to_int(row["code"])
    if code not in _RRC_PROCS:
        return None
    direction = "dl" if code in _DL_PROCS else "ul"
    # SRB0 is CCCH. InitialULRRCMessageTransfer (11) carries no SRBID but is always on SRB0.
    if code == 11 or to_int(row["srbid"]) == 0:
        return decode_ccch_type(row["rrc_container"], direction)
    # A DCCH container of a UEContextReleaseCommand is PDCP-protected, and in OCUDU it is an rrcRelease.
    if code == 6:
        return "rrcRelease?"
    return "(undissected)"


def _rrc_field(msg: str) -> str:
    return f"nr-rrc.{msg}_element"


def _build_clusters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    by_cu: dict[str, dict[str, Any]] = {}
    by_du: dict[str, dict[str, Any]] = {}
    for row in rows:
        # Rows without UE identifiers are procedures of the interface, e.g. F1Setup.
        if not (row["cu_ue_id"] or row["du_ue_id"] or row["crnti"]):
            continue
        c = None
        if row["cu_ue_id"] and row["cu_ue_id"] in by_cu:
            c = by_cu[row["cu_ue_id"]]
        if c is None and row["du_ue_id"] and row["du_ue_id"] in by_du:
            c = by_du[row["du_ue_id"]]
        if c is None:
            c = {
                "frame": row["frame"],
                "first_epoch": row["epoch"],
                "first_code": row["code"],
                "cu_ue_f1ap_id": None,
                "du_ue_f1ap_ids": set(),
                "crntis": set(),
            }
            clusters.append(c)
        if row["epoch"] < c["first_epoch"]:
            c["first_epoch"] = row["epoch"]
            c["frame"] = row["frame"]
            c["first_code"] = row["code"]
        if row["cu_ue_id"]:
            if c["cu_ue_f1ap_id"] is None:
                c["cu_ue_f1ap_id"] = row["cu_ue_id"]
            by_cu[row["cu_ue_id"]] = c
        if row["du_ue_id"]:
            c["du_ue_f1ap_ids"].add(row["du_ue_id"])
            by_du[row["du_ue_id"]] = c
        if row["crnti"]:
            c["crntis"].add(row["crnti"])
    return clusters
