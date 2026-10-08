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
    ue_fields = UE_ID_FIELDS[proto]
    fields = [
        "frame.number",
        "frame.time_epoch",
        f"{proto}.procedureCode",
        f"{proto}.successfulOutcome_element",
        f"{proto}.unsuccessfulOutcome_element",
        "_ws.col.Info",
        CAUSE_FIELDS[proto],
        *(f for _, f in ue_fields),
    ]
    out = []
    for frame, epoch, code, successful, unsuccessful, info, cause, *ids in tshark.iter_fields(
        pcap, fields, tag=f"{proto}-messages-v2"
    ):
        if not frame or not epoch:
            continue
        out.append({
            "frame": int(frame),
            "epoch": float(epoch),
            "code": code,
            "procedure": proc_name(proto, code, with_code=False),
            "outcome": "unsuccessful" if unsuccessful else "successful" if successful else "initiating",
            "info": info,
            **{label: value or None for (label, _), value in zip(ue_fields, ids)},
            "cause": cause or None,
        })
    return out
