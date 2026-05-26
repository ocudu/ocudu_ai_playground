#!/usr/bin/env python3
"""Per-UE NGAP identity table.

Clusters NGAP rows by `RAN-UE-NGAP-ID`, attaching `AMF-UE-NGAP-ID` once the
AMF assigns it (from InitialContextSetupRequest onwards). Infrastructure
messages (NGSetup, AMFConfigurationUpdate, ...) that don't reference a UE
are skipped.

Usage:
    ngap_ue_ids.py <ngap.pcap>
    ngap_ue_ids.py <ngap.pcap> --ue 42  # filter by any identifier value
    ngap_ue_ids.py <ngap.pcap> --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import utils

FIELDS = [
    "frame.number",
    "frame.time_epoch",
    "ngap.procedureCode",
    "ngap.RAN_UE_NGAP_ID",
    "ngap.AMF_UE_NGAP_ID",
]

# Procedure-code → human name, verified against an OCUDU ngap.pcap.
PROC_NAMES: dict[str, str] = {
    "0":  "AMFConfigurationUpdate",
    "1":  "RANConfigurationUpdate",
    "14": "InitialContextSetup",
    "15": "InitialUEMessage",
    "16": "NASNonDeliveryIndication",
    "21": "NGSetup",
    "27": "Paging",
    "29": "PDUSessionResourceSetup",
    "36": "UEContextModification",
    "41": "UEContextRelease",
    "46": "UplinkNASTransport",
    "47": "DownlinkNASTransport",
}


def proc_name(code: str | None) -> str:
    if code is None or code == "":
        return "?"
    return PROC_NAMES.get(code, f"proc-{code}")


def build_clusters(rows: list[dict]) -> list[dict]:
    clusters: list[dict] = []
    by_ran: dict[str, dict] = {}

    for row in rows:
        if not (row["ran_ue_id"] or row["amf_ue_id"]):
            continue  # infrastructure (NGSetup, AMFConfigurationUpdate, ...)
        c = None
        if row["ran_ue_id"] and row["ran_ue_id"] in by_ran:
            c = by_ran[row["ran_ue_id"]]
        if c is None:
            c = {
                "frame": row["frame"],
                "first_epoch": row["epoch"],
                "first_code": row["code"],
                "ran_ue_ngap_id": None,
                "amf_ue_ngap_id": None,
            }
            clusters.append(c)
        if row["epoch"] < c["first_epoch"]:
            c["first_epoch"] = row["epoch"]
            c["frame"] = row["frame"]
            c["first_code"] = row["code"]
        if row["ran_ue_id"]:
            if c["ran_ue_ngap_id"] is None:
                c["ran_ue_ngap_id"] = row["ran_ue_id"]
            by_ran[row["ran_ue_id"]] = c
        if row["amf_ue_id"] and c["amf_ue_ngap_id"] is None:
            c["amf_ue_ngap_id"] = row["amf_ue_id"]

    return clusters


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcap", help="path to ngap.pcap")
    ap.add_argument("--ue", help="filter rows mentioning this identifier value")
    ap.add_argument("--limit", type=int, default=200,
                    help="cap text output rows (default 200; use 0 for no cap)")
    ap.add_argument("--no-cache", action="store_true",
                    help="bypass /tmp tshark-extraction cache and re-run tshark")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    pcap = Path(args.pcap)
    if not pcap.is_file():
        print(f"error: not a file: {pcap}", file=sys.stderr)
        return 1

    rows: list[dict] = []
    try:
        for r in utils.iter_fields_cached(pcap, FIELDS, tag="ngap-ue-ids-v1",
                                          force=args.no_cache):
            frame, epoch, code, ran_id, amf_id = r
            if not epoch:
                continue
            rows.append({
                "frame": int(frame) if frame else None,
                "epoch": float(epoch),
                "code": code,
                "ran_ue_id": ran_id or None,
                "amf_ue_id": amf_id or None,
            })
    except utils.TsharkError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    clusters = sorted(build_clusters(rows), key=lambda c: c["first_epoch"])

    out_list = [
        {
            "frame": c["frame"],
            "first_iso": utils.epoch_to_iso(c["first_epoch"]),
            "message": proc_name(c["first_code"]),
            "ran_ue_ngap_id": c["ran_ue_ngap_id"],
            "amf_ue_ngap_id": c["amf_ue_ngap_id"],
            "first_epoch": c["first_epoch"],
        }
        for c in clusters
    ]

    if args.ue:
        u = args.ue
        out_list = [r for r in out_list
                    if u == r["ran_ue_ngap_id"] or u == r["amf_ue_ngap_id"]]

    if args.json:
        print(json.dumps(out_list, indent=2))
        return 0

    if not out_list:
        print("(no NGAP UEs matched)")
        return 0
    header = ("frame", "first_iso", "message", "ran_ue_ngap_id", "amf_ue_ngap_id")
    print(", ".join(header))
    rendered = out_list if args.limit <= 0 else out_list[: args.limit]
    for r in rendered:
        print(", ".join([
            str(r["frame"]) if r["frame"] is not None else "-",
            r["first_iso"],
            r["message"],
            r["ran_ue_ngap_id"] or "-",
            r["amf_ue_ngap_id"] or "-",
        ]))
    if args.limit > 0 and len(out_list) > args.limit:
        print(f"... {len(out_list) - args.limit} more rows truncated (use --limit 0 to show all)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
