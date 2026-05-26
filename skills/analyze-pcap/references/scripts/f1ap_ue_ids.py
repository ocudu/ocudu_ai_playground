#!/usr/bin/env python3
"""Per-UE F1AP identity table.

Clusters F1AP rows by the CU-assigned `gNB-CU-UE-F1AP-ID` when available,
falling back to the DU-assigned `gNB-DU-UE-F1AP-ID` for rows from
InitialULRRCMessageTransfer (where the CU ID is not yet set). Each output row
is one UE seen in F1AP, with the frame and timestamp of the first sighting.

Usage:
    f1ap_ue_ids.py <f1ap.pcap>
    f1ap_ue_ids.py <f1ap.pcap> --ue 5   # filter by any identifier value
    f1ap_ue_ids.py <f1ap.pcap> --json
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
    "f1ap.procedureCode",
    "f1ap.GNB_DU_UE_F1AP_ID",
    "f1ap.GNB_CU_UE_F1AP_ID",
    "f1ap.C_RNTI",
]

# Procedure-code → human name, verified against an OCUDU f1ap.pcap.
PROC_NAMES: dict[str, str] = {
    "1":  "F1Setup",
    "5":  "UEContextSetup",
    "6":  "UEContextRelease",
    "7":  "UEContextModification",
    "11": "InitialULRRCMessageTransfer",
    "12": "DLRRCMessageTransfer",
    "13": "ULRRCMessageTransfer",
}


def proc_name(code: str | None) -> str:
    if code is None or code == "":
        return "?"
    return PROC_NAMES.get(code, f"proc-{code}")


def build_clusters(rows: list[dict]) -> list[dict]:
    clusters: list[dict] = []
    by_cu: dict[str, dict] = {}
    by_du: dict[str, dict] = {}

    for row in rows:
        if not (row["cu_ue_id"] or row["du_ue_id"] or row["crnti"]):
            continue  # infrastructure (F1Setup, GNB-{CU,DU}-ConfigurationUpdate, ...)
        c = None
        if row["cu_ue_id"] and row["cu_ue_id"] in by_cu:
            c = by_cu[row["cu_ue_id"]]
        if c is None and row["du_ue_id"] and row["du_ue_id"] in by_du:
            c = by_du[row["du_ue_id"]]
        if c is None:
            c = {
                "frame": row["frame"],
                "first_epoch": row["epoch"],
                "first_code": row["code"],
                "cu_ue_f1ap_id": None,
                "du_ue_f1ap_ids": set(),
                "crntis": set(),
            }
            clusters.append(c)
        if row["epoch"] < c["first_epoch"]:
            c["first_epoch"] = row["epoch"]
            c["frame"] = row["frame"]
            c["first_code"] = row["code"]
        if row["cu_ue_id"]:
            if c["cu_ue_f1ap_id"] is None:
                c["cu_ue_f1ap_id"] = row["cu_ue_id"]
            by_cu[row["cu_ue_id"]] = c
        if row["du_ue_id"]:
            c["du_ue_f1ap_ids"].add(row["du_ue_id"])
            by_du[row["du_ue_id"]] = c
        if row["crnti"]:
            c["crntis"].add(row["crnti"])

    return clusters


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcap", help="path to f1ap.pcap")
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
        for r in utils.iter_fields_cached(pcap, FIELDS, tag="f1ap-ue-ids-v1",
                                          force=args.no_cache):
            frame, epoch, code, du_id, cu_id, crnti = r
            if not epoch:
                continue
            rows.append({
                "frame": int(frame) if frame else None,
                "epoch": float(epoch),
                "code": code,
                "du_ue_id": du_id or None,
                "cu_ue_id": cu_id or None,
                "crnti": crnti or None,
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
            "cu_ue_f1ap_id": c["cu_ue_f1ap_id"],
            "du_ue_f1ap_ids": sorted(c["du_ue_f1ap_ids"]),
            "crntis": sorted(c["crntis"]),
            "first_epoch": c["first_epoch"],
        }
        for c in clusters
    ]

    if args.ue:
        u = args.ue
        out_list = [
            r for r in out_list
            if u == r["cu_ue_f1ap_id"]
            or u in r["du_ue_f1ap_ids"]
            or u in r["crntis"]
        ]

    if args.json:
        print(json.dumps(out_list, indent=2))
        return 0

    if not out_list:
        print("(no F1AP UEs matched)")
        return 0
    header = ("frame", "first_iso", "message", "cu_ue_f1ap_id",
              "du_ue_f1ap_ids", "crntis")
    print(", ".join(header))
    rendered = out_list if args.limit <= 0 else out_list[: args.limit]
    for r in rendered:
        print(", ".join([
            str(r["frame"]) if r["frame"] is not None else "-",
            r["first_iso"],
            r["message"],
            r["cu_ue_f1ap_id"] or "-",
            ";".join(r["du_ue_f1ap_ids"]) or "-",
            ";".join(r["crntis"]) or "-",
        ]))
    if args.limit > 0 and len(out_list) > args.limit:
        print(f"... {len(out_list) - args.limit} more rows truncated (use --limit 0 to show all)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
