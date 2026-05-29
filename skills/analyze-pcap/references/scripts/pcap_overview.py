#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

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

# Each "ue" entry is a list of (label, tshark_field) pairs. Labels are reported
# separately so an NGAP UE with ran_ue_ngap_id=0 and amf_ue_ngap_id=100 doesn't
# look like two distinct UEs.
PROTO_FIELDS: dict[str, dict] = {
    "ngap": {
        "proc": ["ngap.procedureCode"],
        "ue": [("ran", "ngap.RAN_UE_NGAP_ID"), ("amf", "ngap.AMF_UE_NGAP_ID")],
        # Count only true protocol failures (unsuccessfulOutcome). A `cause` IE
        # also rides on normal messages (e.g. UEContextReleaseCommand with
        # user-inactivity), so it must NOT be treated as a failure.
        "failure_filter": "ngap.unsuccessfulOutcome_element",
    },
    "f1ap": {
        "proc": ["f1ap.procedureCode"],
        "ue": [("du", "f1ap.GNB_DU_UE_F1AP_ID"), ("cu", "f1ap.GNB_CU_UE_F1AP_ID")],
        "failure_filter": "f1ap.unsuccessfulOutcome_element",
    },
    "e1ap": {
        "proc": ["e1ap.procedureCode"],
        "ue": [("cp", "e1ap.GNB_CU_CP_UE_E1AP_ID"), ("up", "e1ap.GNB_CU_UP_UE_E1AP_ID")],
        "failure_filter": "e1ap.unsuccessfulOutcome_element",
    },
    "mac": {
        "proc": [],
        "ue": [("rnti", "mac-nr.rnti")],
        "failure_filter": None,
    },
    "rlc": {
        "proc": [],
        "ue": [("ueid", "rlc-nr.ueid")],
        "failure_filter": None,
    },
}


def summarise_pcap(pcap: Path, *, top: int) -> dict:
    proto = pcap.stem  # "ngap", "mac", ...
    spec = PROTO_FIELDS.get(proto)
    out: dict = {"file": str(pcap), "proto": proto}
    fields = ["frame.time_epoch"]
    if spec:
        fields += spec["proc"] + [f for _, f in spec["ue"]]

    rows = list(utils.iter_fields_cached(pcap, fields, tag=f"overview-{proto}-v3"))
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
        # Track distinct values per ID-type separately, so e.g. a single NGAP
        # UE doesn't look like two distinct UEs just because it has both
        # RAN-UE-NGAP-ID and AMF-UE-NGAP-ID populated.
        per_label: dict[str, set[str]] = {label: set() for label, _ in spec["ue"]}
        for r in rows:
            for (label, _), val in zip(spec["ue"], r[ue_start : ue_start + len(spec["ue"])]):
                if val:
                    per_label[label].add(val)
        out["distinct_ues_by_label"] = {k: sorted(v) for k, v in per_label.items()}
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
        if "distinct_ues_by_label" in s:
            parts = []
            for label, vals in s["distinct_ues_by_label"].items():
                if not vals:
                    continue
                if len(vals) <= 5:
                    parts.append(f"{label}({len(vals)})={','.join(vals)}")
                else:
                    parts.append(f"{label}({len(vals)})={','.join(vals[:5])},…")
            if parts:
                lines.append(f"  ues:     {'  '.join(parts)}")
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
