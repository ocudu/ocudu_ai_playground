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
See references/pcap/reference/protocols/f1ap.md § "RRC PDUs inside F1AP containers".

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
from parsers.pcap import f1ap


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
        records = f1ap.messages(utils.TSHARK, pcap, force=args.no_cache)
    except utils.TsharkError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.ue:
        records = [x for x in records if args.ue in (x["cu_ue_f1ap_id"], x["du_ue_f1ap_id"], x["crnti"])]
    if args.rrc:
        records = [x for x in records if x["rrc"]]
    if args.nas:
        records = [x for x in records if x["nas"]]

    if args.json:
        print(json.dumps(records, indent=2))
        return 0

    if not records:
        print("(no F1AP messages matched)")
        return 0
    header = ("frame", "first_iso", "message", "rrc", "nas", "cu_ue_f1ap_id", "du_ue_f1ap_id", "crnti")
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
