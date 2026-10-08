# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Procedure codes of NGAP (TS 38.413), F1AP (TS 38.473) and E1AP (TS 37.483) and their names."""

from __future__ import annotations

# procedureCode to name, per protocol.
PROC_CODE_NAMES: dict[str, dict[int, str]] = {
    "ngap": {
        0: "AMFConfigurationUpdate",
        4: "DownlinkNASTransport",
        14: "InitialContextSetup",
        15: "InitialUEMessage",
        19: "NASNonDeliveryIndication",
        21: "NGSetup",
        24: "Paging",
        28: "PDUSessionResourceRelease",
        29: "PDUSessionResourceSetup",
        35: "RANConfigurationUpdate",
        40: "UEContextModification",
        41: "UEContextRelease",
        44: "UERadioCapabilityInfoIndication",
        46: "UplinkNASTransport",
    },
    "f1ap": {
        1: "F1Setup",
        5: "UEContextSetup",
        6: "UEContextRelease",
        7: "UEContextModification",
        11: "InitialULRRCMessageTransfer",
        12: "DLRRCMessageTransfer",
        13: "ULRRCMessageTransfer",
        26: "F1Removal",
    },
    "e1ap": {
        3: "gNB-CU-UP-E1Setup",
        4: "gNB-CU-CP-E1Setup",
        5: "gNB-CU-UP-ConfigurationUpdate",
        6: "gNB-CU-CP-ConfigurationUpdate",
        7: "E1Release",
        8: "bearerContextSetup",
        9: "bearerContextModification",
        10: "bearerContextModificationRequired",
        11: "bearerContextRelease",
        12: "bearerContextReleaseRequest",
    },
}


def proc_name(proto: str, code: str | int | None, *, with_code: bool = True) -> str:
    """Name of a procedureCode of ngap, f1ap or e1ap, as "Name(code)", or "Name" without with_code.

    Unknown codes give the bare number, or "proc-<n>" without with_code. An empty code gives "?" without with_code.
    """
    if code is None or code == "":
        return str(code) if with_code else "?"
    try:
        c = int(code)
    except (TypeError, ValueError):
        return str(code)
    name = PROC_CODE_NAMES.get(proto, {}).get(c)
    if name is None:
        return str(c) if with_code else f"proc-{c}"
    return f"{name}({c})" if with_code else name
