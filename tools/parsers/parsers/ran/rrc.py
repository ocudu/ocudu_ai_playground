# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""RRC message types (TS 38.331), and the type of CCCH messages from their encoding."""

from __future__ import annotations

# Top-level RRC message types, by logical channel and direction.
RRC_MESSAGE_TYPES = [
    # UL-CCCH.
    "rrcSetupRequest", "rrcResumeRequest", "rrcReestablishmentRequest", "rrcSystemInfoRequest",
    # DL-CCCH.
    "rrcReject", "rrcSetup",
    # DL-DCCH.
    "rrcReconfiguration", "rrcResume", "rrcRelease", "rrcReestablishment",
    "securityModeCommand", "dlInformationTransfer", "ueCapabilityEnquiry",
    "counterCheck", "mobilityFromNRCommand", "ueInformationRequest",
    # UL-DCCH.
    "measurementReport", "rrcReconfigurationComplete", "rrcSetupComplete",
    "rrcReestablishmentComplete", "rrcResumeComplete", "securityModeComplete",
    "securityModeFailure", "ulInformationTransfer", "ueCapabilityInformation",
    "counterCheckResponse", "ueAssistanceInformation", "failureInformation",
]


def decode_ccch_type(container_hex: str, direction: str) -> str | None:
    """RRC message type of a CCCH container, "dl" or "ul", from its first bits, or None if not a c1 message.

    {DL,UL}-CCCH-Message ::= message CHOICE { c1 (2-bit index), messageClassExtension }.
    """
    try:
        b = bytes.fromhex(container_hex)
    except ValueError:
        return None
    if not b or (b[0] >> 7) & 1:
        return None
    idx = (b[0] >> 5) & 0b11
    dl = {0: "rrcReject", 1: "rrcSetup"}
    ul = {0: "rrcSetupRequest", 1: "rrcResumeRequest", 2: "rrcReestablishmentRequest", 3: "rrcSystemInfoRequest"}
    return (dl if direction == "dl" else ul).get(idx)
