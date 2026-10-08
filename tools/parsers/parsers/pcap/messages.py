# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Messages of NGAP, F1AP and E1AP pcaps, with their procedure, outcome, UE identifiers and cause."""

from __future__ import annotations

import os
from typing import Any

from ..ran.procedures import proc_name
from .tshark import Tshark

# UE identifier fields of each protocol, by label.
UE_ID_FIELDS: dict[str, list[tuple[str, str]]] = {
    "ngap": [("ran_ue_ngap_id", "ngap.RAN_UE_NGAP_ID"), ("amf_ue_ngap_id", "ngap.AMF_UE_NGAP_ID")],
    "f1ap": [("du_ue_f1ap_id", "f1ap.GNB_DU_UE_F1AP_ID"), ("cu_ue_f1ap_id", "f1ap.GNB_CU_UE_F1AP_ID")],
    "e1ap": [("cu_cp_ue_e1ap_id", "e1ap.GNB_CU_CP_UE_E1AP_ID"), ("cu_up_ue_e1ap_id", "e1ap.GNB_CU_UP_UE_E1AP_ID")],
}
# Fields of the cause of a message, of the protocols that have one.
CAUSE_FIELDS = {"ngap": "ngap.cause", "f1ap": "f1ap.cause", "e1ap": "e1ap.cause"}


def messages(tshark: Tshark, pcap: str | os.PathLike[str], proto: str) -> list[dict[str, Any]]:
    """The messages of a pcap of proto, "ngap", "f1ap" or "e1ap", in file order.

    Each has "frame", "epoch", "code", "procedure" (its name), "outcome" ("initiating", "successful" or
    "unsuccessful"), "info" (the tshark summary, naming the message), the UE identifiers of UE_ID_FIELDS by label, None
    when absent, and "cause".
    """
    names = fields(proto)
    rows = (dict(zip(names, values)) for values in tshark.iter_fields(pcap, names, tag=f"{proto}-messages-v2"))
    return [m for row in rows if (m := message(proto, row)) is not None]


def fields(proto: str) -> list[str]:
    """The tshark fields of the messages of proto, read by message()."""
    return [
        "frame.number",
        "frame.time_epoch",
        f"{proto}.procedureCode",
        f"{proto}.successfulOutcome_element",
        f"{proto}.unsuccessfulOutcome_element",
        "_ws.col.Info",
        CAUSE_FIELDS[proto],
        *(f for _, f in UE_ID_FIELDS[proto]),
    ]


def message(proto: str, row: dict[str, str]) -> dict[str, Any] | None:
    """The message of proto in a frame, given its tshark field values by name, see messages(), or None without a frame
    number or time.
    """
    frame, epoch, code = row["frame.number"], row["frame.time_epoch"], row[f"{proto}.procedureCode"]
    if not frame or not epoch:
        return None
    if row[f"{proto}.unsuccessfulOutcome_element"]:
        outcome = "unsuccessful"
    elif row[f"{proto}.successfulOutcome_element"]:
        outcome = "successful"
    else:
        outcome = "initiating"
    return {
        "frame": int(frame),
        "epoch": float(epoch),
        "code": code,
        "procedure": proc_name(proto, code, with_code=False),
        "outcome": outcome,
        "info": row["_ws.col.Info"],
        **{label: row[f] or None for label, f in UE_ID_FIELDS[proto]},
        "cause": row[CAUSE_FIELDS[proto]] or None,
    }
