#!/usr/bin/env python3
"""Per-UE chronological NGAP procedure sequence.

Usage:
    ngap_procedures.py <ngap.pcap>
    ngap_procedures.py <ngap.pcap> --ue 42
    ngap_procedures.py <ngap.pcap> --failures-only
    ngap_procedures.py <ngap.pcap> --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import utils

FIELDS = [
    "frame.number",
    "frame.time_epoch",
    "ngap.procedureCode",
    "ngap.RAN_UE_NGAP_ID",
    "ngap.AMF_UE_NGAP_ID",
    "ngap.unsuccessfulOutcome_element",
    "ngap.cause",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcap", help="path to ngap.pcap")
    ap.add_argument("--ue", help="filter to one RAN-UE-NGAP-ID")
    ap.add_argument("--failures-only", action="store_true", help="only show unsuccessful outcomes / with cause")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    pcap = Path(args.pcap)
    if not pcap.is_file():
        print(f"error: not a file: {pcap}", file=sys.stderr)
        return 1

    display_filter = None
    if args.ue:
        display_filter = f"ngap.RAN_UE_NGAP_ID == {args.ue}"
    if args.failures_only:
        unsuccess = "ngap.unsuccessfulOutcome_element || ngap.cause"
        display_filter = f"({display_filter}) && ({unsuccess})" if display_filter else unsuccess

    try:
        rows = list(
            utils.iter_fields_cached(
                pcap,
                FIELDS,
                display_filter=display_filter,
                tag=f"ngap-proc-{args.ue or 'all'}-{int(args.failures_only)}",
            )
        )
    except utils.TsharkError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    by_ue: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        frame, epoch, code, ran_id, amf_id, unsucc, cause = r
        ran_key = ran_id or "(no-ran-ue-id)"
        by_ue[ran_key].append(
            {
                "frame": int(frame) if frame else None,
                "epoch": float(epoch) if epoch else None,
                "iso": utils.epoch_to_iso(epoch) if epoch else None,
                "procedureCode": code,
                "amfUeId": amf_id or None,
                "failure": bool(unsucc) or bool(cause),
                "cause": cause or None,
            }
        )

    if args.json:
        print(json.dumps(by_ue, indent=2))
        return 0

    if not by_ue:
        print("(no matching NGAP rows)")
        return 0

    for ue, events in by_ue.items():
        print(f"== RAN-UE-NGAP-ID={ue}  ({len(events)} events)")
        for e in events:
            marker = "!" if e["failure"] else " "
            cause = f"  cause={e['cause']}" if e["cause"] else ""
            print(
                f"  {marker} frame={e['frame']:>5} {e['iso']}  "
                f"procCode={e['procedureCode']:<3}"
                f"  amfUeId={e['amfUeId'] or '-'}{cause}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
