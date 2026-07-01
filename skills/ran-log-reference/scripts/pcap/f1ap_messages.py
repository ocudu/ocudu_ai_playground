#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Per-message F1AP timeline with decoded RRC and NAS message types.

One output row per F1AP message (frame), in CSV/table style:

    frame, first_iso, message, rrc, nas, cu_ue_f1ap_id, du_ue_f1ap_id, crnti

- `message` is the F1AP procedure name (InitialULRRCMessageTransfer, ...).
- `rrc` is the RRC message type carried in the F1AP RRC-Container IE, if any.
- `nas` is the NAS (5GMM/5GSM) message type carried inside that RRC, if any.
- the RRC and NAS columns come *before* the UE identifiers, as requested.

The RRC type comes from tshark's own dissection (`nr-rrc.<type>_element`) where
tshark decodes the container. tshark does NOT dissect the RRC-Container inside a
UEContextReleaseCommand (proc 6), so for those the top-level CCCH message type is
decoded here from the container bits (a 1-bit message CHOICE + 2-bit c1 index —
DL-CCCH: 0=rrcReject, 1=rrcSetup). A UEContextReleaseCommand DCCH container is
PDCP-protected / not dissected and is reported as `rrcRelease?` (inferred).
See references/pcap/protocols/f1ap.md § "RRC PDUs inside F1AP containers".

Usage:
    f1ap_messages.py <f1ap.pcap>
    f1ap_messages.py <f1ap.pcap> --ue 640      # filter by any UE identifier value
    f1ap_messages.py <f1ap.pcap> --rrc         # only rows carrying an RRC message
    f1ap_messages.py <f1ap.pcap> --nas         # only rows carrying a NAS message
    f1ap_messages.py <f1ap.pcap> --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import utils

# Scalar columns first, then the NAS type codes, then the RRC message-type
# probe fields. Order within RRC_ELEMENT_FIELDS is irrelevant (only one
# top-level message-type element fires per frame).
SCALAR_FIELDS = [
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

# RRC top-level message types (TS 38.331). tshark exposes each as a
# `nr-rrc.<name>_element` field that emits a token when present.
RRC_MESSAGE_TYPES = [
    # UL-CCCH
    "rrcSetupRequest", "rrcResumeRequest", "rrcReestablishmentRequest", "rrcSystemInfoRequest",
    # DL-CCCH
    "rrcReject", "rrcSetup",
    # DL-DCCH
    "rrcReconfiguration", "rrcResume", "rrcRelease", "rrcReestablishment",
    "securityModeCommand", "dlInformationTransfer", "ueCapabilityEnquiry",
    "counterCheck", "mobilityFromNRCommand", "ueInformationRequest",
    # UL-DCCH
    "measurementReport", "rrcReconfigurationComplete", "rrcSetupComplete",
    "rrcReestablishmentComplete", "rrcResumeComplete", "securityModeComplete",
    "securityModeFailure", "ulInformationTransfer", "ueCapabilityInformation",
    "counterCheckResponse", "ueAssistanceInformation", "failureInformation",
]
def _rrc_field(msg: str) -> str:
    return f"nr-rrc.{msg}_element"


# NAS naming and the generic tshark field-validation live in utils (reusable by
# the NGAP scripts, which also carry NAS). RRC decoding below stays local — no
# other pcap type in this toolset carries RRC.

# DL-direction procedures (CU -> DU -> UE). Others in RRC_PROCS are UL.
_DL_PROCS = {5, 6, 7, 12}
_RRC_PROCS = {5, 6, 7, 11, 12, 13}


def valid_rrc_messages(pcap: Path) -> list[str]:
    """RRC message types whose tshark `_element` field this build recognizes."""
    valid = set(utils.filter_valid_fields(pcap, [_rrc_field(m) for m in RRC_MESSAGE_TYPES]))
    return [m for m in RRC_MESSAGE_TYPES if _rrc_field(m) in valid]


def decode_ccch_type(container_hex: str, direction: str) -> str | None:
    """Decode the top-level CCCH RRC message type from the container bits.

    {DL,UL}-CCCH-Message ::= message CHOICE { c1 (2-bit index), messageClassExtension }.
    Only valid for CCCH (SRB0). Returns None if the first CHOICE is not c1.
    """
    try:
        b = bytes.fromhex(container_hex)
    except ValueError:
        return None
    if not b:
        return None
    v = b[0]
    if (v >> 7) & 1:  # message CHOICE != c1 (messageClassExtension)
        return None
    idx = (v >> 5) & 0b11  # 2-bit c1 index
    dl = {0: "rrcReject", 1: "rrcSetup"}
    ul = {0: "rrcSetupRequest", 1: "rrcResumeRequest",
          2: "rrcReestablishmentRequest", 3: "rrcSystemInfoRequest"}
    return (dl if direction == "dl" else ul).get(idx)


def resolve_rrc(row: dict) -> str | None:
    """RRC message type for a row: tshark's dissection, else a manual decode."""
    # tshark decoded it: exactly one message-type element field is non-empty.
    for name, val in row["rrc_elements"].items():
        if val:
            return name
    # Not dissected (UEContextReleaseCommand container). Decode / infer.
    if not row["rrc_container"]:
        return None
    code = utils.to_int(row["code"])
    if code not in _RRC_PROCS:
        return None
    direction = "dl" if code in _DL_PROCS else "ul"
    # The SRB ID picks the logical channel: SRB0 ⇒ CCCH, SRB1/2 ⇒ DCCH. The
    # rrcReject in a UEContextReleaseCommand is always sent on SRB0, so it is a
    # DL-CCCH-Message (decodable). InitialULRRCMessageTransfer (11) carries no
    # SRBID but is UL-CCCH (SRB0) by definition.
    srb = utils.to_int(row["srbid"])
    is_ccch = (code == 11) or (srb == 0)
    if is_ccch:
        return decode_ccch_type(row["rrc_container"], direction)
    # DCCH container in a UEContextReleaseCommand: PDCP-protected / not
    # dissected; in this stack it is an rrcRelease. Flag the inference.
    if code == 6:
        return "rrcRelease?"
    return "(undissected)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcap", help="path to f1ap.pcap")
    ap.add_argument("--ue", help="filter rows mentioning this identifier value (cu/du F1AP ID or C-RNTI)")
    ap.add_argument("--rrc", action="store_true", help="only rows that carry an RRC message")
    ap.add_argument("--nas", action="store_true", help="only rows that carry a NAS message")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap text output rows (default 0 = no cap; set a positive N to cap)")
    ap.add_argument("--no-cache", action="store_true",
                    help="bypass /tmp tshark-extraction cache and re-run tshark")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    pcap = Path(args.pcap)
    if not pcap.is_file():
        print(f"error: not a file: {pcap}", file=sys.stderr)
        return 1

    try:
        rrc_msgs = valid_rrc_messages(pcap)
    except utils.TsharkError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    fields = SCALAR_FIELDS + [_rrc_field(m) for m in rrc_msgs]
    n_scalar = len(SCALAR_FIELDS)
    out_list: list[dict] = []
    try:
        for r in utils.iter_fields_cached(pcap, fields,
                                          tag=f"f1ap-messages-v1-{len(fields)}",
                                          force=args.no_cache):
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
                "rrc_elements": dict(zip(rrc_msgs, r[n_scalar:])),
            }
            row["rrc"] = resolve_rrc(row)
            row["nas"] = utils.nas_name(nas_mm, nas_sm)
            out_list.append(row)
    except utils.TsharkError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    out_list.sort(key=lambda x: x["epoch"])

    if args.ue:
        u = args.ue
        out_list = [x for x in out_list
                    if u in (x["cu_ue_id"], x["du_ue_id"], x["crnti"])]
    if args.rrc:
        out_list = [x for x in out_list if x["rrc"]]
    if args.nas:
        out_list = [x for x in out_list if x["nas"]]

    records = [
        {
            "frame": x["frame"],
            "first_iso": utils.epoch_to_iso(x["epoch"]),
            "message": utils.proc_name("f1ap", x["code"], with_code=False),
            "rrc": x["rrc"],
            "nas": x["nas"],
            "cu_ue_f1ap_id": x["cu_ue_id"],
            "du_ue_f1ap_id": x["du_ue_id"],
            "crnti": x["crnti"],
        }
        for x in out_list
    ]

    if args.json:
        print(json.dumps(records, indent=2))
        return 0

    if not records:
        print("(no F1AP messages matched)")
        return 0
    header = ("frame", "first_iso", "message", "rrc", "nas",
              "cu_ue_f1ap_id", "du_ue_f1ap_id", "crnti")
    print(", ".join(header))
    rendered = records if args.limit <= 0 else records[: args.limit]
    for x in rendered:
        print(", ".join([
            str(x["frame"]) if x["frame"] is not None else "-",
            x["first_iso"],
            x["message"],
            x["rrc"] or "-",
            x["nas"] or "-",
            x["cu_ue_f1ap_id"] or "-",
            x["du_ue_f1ap_id"] or "-",
            x["crnti"] or "-",
        ]))
    if args.limit > 0 and len(records) > args.limit:
        print(f"... {len(records) - args.limit} more rows truncated (use --limit 0 to show all)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
