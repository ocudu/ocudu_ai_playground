# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""RRC message types (TS 38.331), and the type of CCCH messages from their encoding."""

from __future__ import annotations

# Top-level RRC message types, by logical channel and direction, as the fields of tshark name them.
RRC_MESSAGE_TYPES = [
    # UL-CCCH and UL-CCCH1.
    "rrcSetupRequest", "rrcResumeRequest", "rrcReestablishmentRequest", "rrcSystemInfoRequest", "rrcResumeRequest1",
    # DL-CCCH.
    "rrcReject", "rrcSetup",
    # DL-DCCH.
    "rrcReconfiguration", "rrcResume", "rrcRelease", "rrcReestablishment",
    "securityModeCommand", "dlInformationTransfer", "ueCapabilityEnquiry",
    "counterCheck", "mobilityFromNRCommand", "ueInformationRequest_r16", "dlDedicatedMessageSegment_r16",
    "dlInformationTransferMRDC_r16", "loggedMeasurementConfiguration_r16",
    # UL-DCCH.
    "measurementReport", "rrcReconfigurationComplete", "rrcSetupComplete",
    "rrcReestablishmentComplete", "rrcResumeComplete", "securityModeComplete",
    "securityModeFailure", "ulInformationTransfer", "ueCapabilityInformation",
    "counterCheckResponse", "ueAssistanceInformation", "failureInformation", "ueInformationResponse_r16",
    "ulDedicatedMessageSegment_r16", "mcgFailureInformation_r16", "locationMeasurementIndication",
    "scgFailureInformation", "scgFailureInformationEUTRA", "ulInformationTransferMRDC", "dedicatedSIBRequest_r16",
    "iabOtherInformation_r16", "ulInformationTransferIRAT_r16", "sidelinkUEInformationNR_r16",
]
# Size of the UL-CCCH1 messages, of 64 bits, whose only one is rrcResumeRequest1; UL-CCCH ones are of 48 bits.
_UL_CCCH1_BYTES = 8


def decode_ccch_type(container_hex: str, direction: str) -> str | None:
    """RRC message type of a CCCH container, "dl" or "ul", from its first bits, or None if not a c1 message.

    {DL,UL}-CCCH-Message ::= message CHOICE { c1 (2-bit index), messageClassExtension }. UL-CCCH1-Message has the same
    structure, its message of 64 bits instead of 48, and only rrcResumeRequest1 in c1.
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
    if direction == "ul" and len(b) == _UL_CCCH1_BYTES:
        ul = {0: "rrcResumeRequest1"}
    return (dl if direction == "dl" else ul).get(idx)
