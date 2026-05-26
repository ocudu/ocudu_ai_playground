#!/usr/bin/env python3
"""Per-UE E1AP identity table.

Clusters E1AP rows by `gNB-CU-CP-UE-E1AP-ID`, attaching `gNB-CU-UP-UE-E1AP-ID`
once the CU-UP responds. Infrastructure messages (E1Setup, status
indications, ...) that carry no per-UE IDs are skipped.

Usage:
    e1ap_ue_ids.py <e1ap.pcap>
    e1ap_ue_ids.py <e1ap.pcap> --ue 7   # filter by any identifier value
    e1ap_ue_ids.py <e1ap.pcap> --json
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
    "e1ap.procedureCode",
    "e1ap.GNB_CU_CP_UE_E1AP_ID",
    "e1ap.GNB_CU_UP_UE_E1AP_ID",
]

# Procedure-code → human name, verified against an OCUDU e1ap.pcap.
PROC_NAMES: dict[str, str] = {
    "3":  "gNB-CU-UP-E1Setup",
    "4":  "gNB-CU-CP-E1Setup",
    "5":  "gNB-CU-UP-ConfigurationUpdate",
    "6":  "gNB-CU-CP-ConfigurationUpdate",
    "7":  "E1Release",
    "8":  "bearerContextSetup",
    "9":  "bearerContextModification",
    "10": "bearerContextModificationRequired",
    "11": "bearerContextRelease",
    "12": "bearerContextReleaseRequest",
}


def proc_name(code: str | None) -> str:
    if code is None or code == "":
        return "?"
    return PROC_NAMES.get(code, f"proc-{code}")


def build_clusters(rows: list[dict]) -> list[dict]:
    clusters: list[dict] = []
    by_cp: dict[str, dict] = {}

    for row in rows:
        if not (row["e1_cp_ue_id"] or row["e1_up_ue_id"]):
            continue  # infrastructure (E1Setup, GNB-CU-UP-StatusIndication, ...)
        c = None
        if row["e1_cp_ue_id"] and row["e1_cp_ue_id"] in by_cp:
            c = by_cp[row["e1_cp_ue_id"]]
        if c is None:
            c = {
                "frame": row["frame"],
                "first_epoch": row["epoch"],
                "first_code": row["code"],
                "e1_cp_ue_id": None,
                "e1_up_ue_id": None,
            }
            clusters.append(c)
        if row["epoch"] < c["first_epoch"]:
            c["first_epoch"] = row["epoch"]
            c["frame"] = row["frame"]
            c["first_code"] = row["code"]
        if row["e1_cp_ue_id"]:
            if c["e1_cp_ue_id"] is None:
                c["e1_cp_ue_id"] = row["e1_cp_ue_id"]
            by_cp[row["e1_cp_ue_id"]] = c
        if row["e1_up_ue_id"] and c["e1_up_ue_id"] is None:
            c["e1_up_ue_id"] = row["e1_up_ue_id"]

    return clusters


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcap", help="path to e1ap.pcap")
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
        for r in utils.iter_fields_cached(pcap, FIELDS, tag="e1ap-ue-ids-v1",
                                          force=args.no_cache):
            frame, epoch, code, cpid, upid = r
            if not epoch:
                continue
            rows.append({
                "frame": int(frame) if frame else None,
                "epoch": float(epoch),
                "code": code,
                "e1_cp_ue_id": cpid or None,
                "e1_up_ue_id": upid or None,
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
            "e1_cp_ue_id": c["e1_cp_ue_id"],
            "e1_up_ue_id": c["e1_up_ue_id"],
            "first_epoch": c["first_epoch"],
        }
        for c in clusters
    ]

    if args.ue:
        u = args.ue
        out_list = [r for r in out_list
                    if u == r["e1_cp_ue_id"] or u == r["e1_up_ue_id"]]

    if args.json:
        print(json.dumps(out_list, indent=2))
        return 0

    if not out_list:
        print("(no E1AP UEs matched)")
        return 0
    header = ("frame", "first_iso", "message", "e1_cp_ue_id", "e1_up_ue_id")
    print(", ".join(header))
    rendered = out_list if args.limit <= 0 else out_list[: args.limit]
    for r in rendered:
        print(", ".join([
            str(r["frame"]) if r["frame"] is not None else "-",
            r["first_iso"],
            r["message"],
            r["e1_cp_ue_id"] or "-",
            r["e1_up_ue_id"] or "-",
        ]))
    if args.limit > 0 and len(out_list) > args.limit:
        print(f"... {len(out_list) - args.limit} more rows truncated (use --limit 0 to show all)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
