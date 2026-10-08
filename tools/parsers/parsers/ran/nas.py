# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""NAS 5GMM and 5GSM message types (TS 24.501 9.7) and their names."""

from __future__ import annotations

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


def nas_name(mm_type: str | int | None, sm_type: str | int | None) -> str | None:
    """Name of a NAS message from its 5GSM type, else its 5GMM type, or None without either."""
    v = _to_int(sm_type)
    if v is not None:
        return NAS_5GSM_TYPES.get(v, f"5GSM(0x{v:02x})")
    v = _to_int(mm_type)
    if v is not None:
        return NAS_5GMM_TYPES.get(v, f"5GMM(0x{v:02x})")
    return None


def _to_int(value: str | int | None) -> int | None:
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return None
