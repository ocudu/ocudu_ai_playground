#!/usr/bin/env python3
"""Compact overview of an OCUDU pcap or run directory.

For each pcap: packet count, duration, first/last epoch, distinct UE IDs,
top procedure codes (or PDU types for MAC/RLC), and count of Failure/Reject
PDUs.

Usage:
    pcap_overview.py <path>              # path is a .pcap or a run directory
    pcap_overview.py <path> --top 5      # show top N procedure codes
    pcap_overview.py <path> --json       # machine-readable output

Exit codes:
    0  - success
    1  - unrecoverable error (file missing, tshark unavailable)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import utils

PROTO_FIELDS: dict[str, dict[str, list[str]]] = {
    "ngap": {
        "proc": ["ngap.procedureCode"],
        "ue": ["ngap.RAN_UE_NGAP_ID", "ngap.AMF_UE_NGAP_ID"],
        "failure_filter": "ngap.unsuccessfulOutcome_element || ngap.cause",
    },
    "f1ap": {
        "proc": ["f1ap.procedureCode"],
        "ue": ["f1ap.GNB_DU_UE_F1AP_ID", "f1ap.GNB_CU_UE_F1AP_ID"],
        "failure_filter": "f1ap.unsuccessfulOutcome_element || f1ap.cause",
    },
    "e1ap": {
        "proc": ["e1ap.procedureCode"],
        "ue": ["e1ap.GNB_CU_CP_UE_E1AP_ID", "e1ap.GNB_CU_UP_UE_E1AP_ID"],
        "failure_filter": "e1ap.unsuccessfulOutcome_element || e1ap.cause",
    },
    "mac": {
        "proc": [],
        "ue": ["mac-nr.rnti"],
        "failure_filter": None,
    },
    "rlc": {
        "proc": [],
        "ue": ["rlc-nr.ueid"],
        "failure_filter": None,
    },
}


def summarise_pcap(pcap: Path, *, top: int) -> dict:
    proto = pcap.stem  # "ngap", "mac", ...
    spec = PROTO_FIELDS.get(proto)
    out: dict = {"file": str(pcap), "proto": proto}
    fields = ["frame.time_epoch"]
    if spec:
        fields += spec["proc"] + spec["ue"]

    rows = list(utils.iter_fields_cached(pcap, fields, tag=f"overview-{proto}"))
    out["packets"] = len(rows)
    if not rows:
        out["empty"] = True
        return out

    epochs = [float(r[0]) for r in rows if r[0]]
    if epochs:
        out["first_epoch"] = min(epochs)
        out["last_epoch"] = max(epochs)
        out["duration_s"] = out["last_epoch"] - out["first_epoch"]
        out["first_iso"] = utils.epoch_to_iso(out["first_epoch"])
        out["last_iso"] = utils.epoch_to_iso(out["last_epoch"])

    if spec and spec["proc"]:
        proc_col = 1
        codes = Counter(r[proc_col] for r in rows if r[proc_col])
        out["top_procedures"] = codes.most_common(top)
    if spec:
        ue_start = 1 + len(spec["proc"])
        ue_vals: set[str] = set()
        for r in rows:
            for c in r[ue_start : ue_start + len(spec["ue"])]:
                if c:
                    ue_vals.add(c)
        out["distinct_ues"] = sorted(ue_vals)
        if spec["failure_filter"]:
            try:
                staged = utils.stage_for_tshark(pcap)
                fail_lines = utils.run_tshark(
                    ["-r", str(staged), "-Y", spec["failure_filter"], "-T", "fields",
                     "-e", "frame.number"]
                )
                out["failures"] = len(fail_lines)
            except utils.TsharkError as e:
                utils.warn(f"failure-count tshark call failed for {pcap}: {e}")
                out["failures"] = None
    return out


def render_text(summaries: list[dict]) -> str:
    lines: list[str] = []
    for s in summaries:
        lines.append(f"== {s['file']} ({s['proto']})")
        if s.get("empty") or s["packets"] == 0:
            lines.append("  (no packets)")
            continue
        lines.append(f"  packets: {s['packets']}")
        lines.append(
            f"  range:   {s.get('first_iso','?')} .. {s.get('last_iso','?')} "
            f"({s.get('duration_s', 0):.3f} s)"
        )
        if "distinct_ues" in s and s["distinct_ues"]:
            lines.append(f"  ues:     {', '.join(s['distinct_ues'])}")
        if "top_procedures" in s and s["top_procedures"]:
            top = ", ".join(f"{code}×{count}" for code, count in s["top_procedures"])
            lines.append(f"  top:     {top}")
        if s.get("failures") is not None:
            lines.append(f"  failures: {s['failures']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help=".pcap file or a run directory")
    ap.add_argument("--top", type=int, default=5, help="top N procedure codes per pcap")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    p = Path(args.path)
    if not p.exists():
        print(f"error: not found: {p}", file=sys.stderr)
        return 1

    targets: list[Path] = []
    if p.is_dir():
        for name in utils.PCAP_NAMES:
            f = p / name
            if f.is_file():
                targets.append(f)
        if not targets:
            print(f"error: no OCUDU pcaps in {p}", file=sys.stderr)
            return 1
    else:
        targets = [p]

    try:
        summaries = [summarise_pcap(t, top=args.top) for t in targets]
    except utils.TsharkError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summaries, indent=2))
    else:
        print(render_text(summaries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
