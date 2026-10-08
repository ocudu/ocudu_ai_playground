# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Names of NGAP, F1AP and E1AP procedure codes and of NAS message types, and conversions of tshark field values."""

from __future__ import annotations

import datetime as _dt

# procedureCode to name, per protocol. Unknown codes fall back to the bare number in proc_name().
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

# NAS 5GMM message type to name (TS 24.501 9.7).
NAS_5GMM_TYPES: dict[int, str] = {
    0x41: "RegistrationRequest", 0x42: "RegistrationAccept", 0x43: "RegistrationComplete",
    0x44: "RegistrationReject", 0x45: "DeregistrationRequest(UEorig)",
    0x46: "DeregistrationAccept(UEorig)", 0x47: "DeregistrationRequest(UEterm)",
    0x48: "DeregistrationAccept(UEterm)", 0x4c: "ServiceRequest", 0x4d: "ServiceReject",
    0x4e: "ServiceAccept", 0x54: "ConfigurationUpdateCommand", 0x55: "ConfigurationUpdateComplete",
    0x56: "AuthenticationRequest", 0x57: "AuthenticationResponse", 0x58: "AuthenticationReject",
    0x59: "AuthenticationFailure", 0x5a: "AuthenticationResult", 0x5b: "IdentityRequest",
    0x5c: "IdentityResponse", 0x5d: "SecurityModeCommand", 0x5e: "SecurityModeComplete",
    0x5f: "SecurityModeReject", 0x64: "5GMMStatus", 0x65: "Notification",
    0x66: "NotificationResponse", 0x67: "DLNASTransport", 0x68: "ULNASTransport",
}
# NAS 5GSM message type to name (TS 24.501 9.7).
NAS_5GSM_TYPES: dict[int, str] = {
    0xc1: "PDUSessionEstablishmentRequest", 0xc2: "PDUSessionEstablishmentAccept",
    0xc3: "PDUSessionEstablishmentReject", 0xc4: "PDUSessionAuthenticationCommand",
    0xc5: "PDUSessionAuthenticationComplete", 0xc6: "PDUSessionAuthenticationResult",
    0xc9: "PDUSessionModificationRequest", 0xca: "PDUSessionModificationReject",
    0xcb: "PDUSessionModificationCommand", 0xcc: "PDUSessionModificationComplete",
    0xcd: "PDUSessionModificationCommandReject", 0xd1: "PDUSessionReleaseRequest",
    0xd2: "PDUSessionReleaseReject", 0xd3: "PDUSessionReleaseCommand",
    0xd4: "PDUSessionReleaseComplete", 0xd6: "5GSMStatus",
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


def nas_name(mm_type: str | int | None, sm_type: str | int | None) -> str | None:
    """Name of a NAS message from its 5GSM type, else its 5GMM type, or None without either."""
    v = to_int(sm_type)
    if v is not None:
        return NAS_5GSM_TYPES.get(v, f"5GSM(0x{v:02x})")
    v = to_int(mm_type)
    if v is not None:
        return NAS_5GMM_TYPES.get(v, f"5GMM(0x{v:02x})")
    return None


def to_int(value: str | int | None, base: int = 0) -> int | None:
    """Integer of a tshark field value, e.g. "0x41" or "65", or None if empty or not a number."""
    try:
        return int(str(value), base)
    except (TypeError, ValueError):
        return None


def epoch_to_iso(epoch: float | str) -> str:
    """UTC ISO-8601 time of an epoch in seconds, with milliseconds and no zone suffix."""
    try:
        ts = float(epoch)
    except (TypeError, ValueError):
        return str(epoch)
    dt = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
