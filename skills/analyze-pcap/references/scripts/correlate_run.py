#!/usr/bin/env python3
"""Unified epoch-sorted timeline across all 5 pcaps in a run directory.

Usage:
    correlate_run.py <run-dir>
    correlate_run.py <run-dir> --around 1747300050 --window-ms 2000
    correlate_run.py <run-dir> --ue 42
    correlate_run.py <run-dir> --protocols ngap,f1ap
    correlate_run.py <run-dir> --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import utils

# Per-protocol field set used to build a one-line summary for each event.
PROTO_SPEC: dict[str, dict[str, list[str]]] = {
    "ngap": {
        "fields": ["frame.number", "frame.time_epoch",
                   "ngap.procedureCode", "ngap.RAN_UE_NGAP_ID", "ngap.AMF_UE_NGAP_ID"],
    },
    "f1ap": {
        "fields": ["frame.number", "frame.time_epoch",
                   "f1ap.procedureCode", "f1ap.GNB_DU_UE_F1AP_ID", "f1ap.GNB_CU_UE_F1AP_ID"],
    },
    "e1ap": {
        "fields": ["frame.number", "frame.time_epoch",
                   "e1ap.procedureCode", "e1ap.GNB_CU_CP_UE_E1AP_ID", "e1ap.GNB_CU_UP_UE_E1AP_ID"],
    },
    "mac": {
        "fields": ["frame.number", "frame.time_epoch",
                   "mac-nr.rnti", "mac-nr.direction"],
    },
    "rlc": {
        "fields": ["frame.number", "frame.time_epoch",
                   "rlc-nr.ueid", "rlc-nr.bearer-type", "rlc-nr.bearer-id"],
    },
}


def collect(pcap: Path, proto: str) -> list[dict]:
    spec = PROTO_SPEC[proto]
    out: list[dict] = []
    for row in utils.iter_fields_cached(pcap, spec["fields"], tag=f"correlate-{proto}"):
        frame, epoch, *rest = row
        if not epoch:
            continue
        try:
            ts = float(epoch)
        except ValueError:
            continue
        ue_ids = [v for v in rest[1:] if v] if proto in ("ngap", "f1ap", "e1ap") else \
                 ([rest[0]] if proto == "mac" and rest[0] else
                  [rest[0]] if proto == "rlc" and rest[0] else [])
        if proto in ("ngap", "f1ap", "e1ap"):
            summary = f"procCode={rest[0]}"
        elif proto == "mac":
            dir_label = {"0": "UL", "1": "DL"}.get(rest[1], rest[1] or "?")
            summary = f"rnti={rest[0] or '-'} dir={dir_label}"
        elif proto == "rlc":
            summary = f"ueid={rest[0] or '-'} bearer={rest[1] or '?'}/{rest[2] or '?'}"
        else:
            summary = ""
        out.append({
            "epoch": ts,
            "iso": utils.epoch_to_iso(ts),
            "file": proto,
            "frame": int(frame) if frame else None,
            "ue_ids": ue_ids,
            "summary": summary,
        })
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", help="OCUDU run directory containing the 5 sibling pcaps")
    ap.add_argument("--around", type=float, help="centre epoch for the window")
    ap.add_argument("--window-ms", type=int, default=2000,
                    help="full window width in ms (centred on --around). Default 2000.")
    ap.add_argument("--ue", help="filter to events mentioning this identifier")
    ap.add_argument("--protocols", default="ngap,f1ap,e1ap,mac,rlc",
                    help="comma-separated subset to include")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not utils.is_run_dir(run_dir):
        print(f"error: not a run directory (need ≥2 of {utils.PCAP_NAMES}): {run_dir}",
              file=sys.stderr)
        return 1

    requested = [p.strip() for p in args.protocols.split(",") if p.strip()]
    sibs = utils.walk_run_dir(run_dir)

    # Check sibling time-range overlap.
    spans: list[tuple[str, float, float]] = []
    events: list[dict] = []
    for proto in requested:
        pcap = sibs.get(proto)
        if pcap is None:
            utils.warn(f"missing {proto}.pcap in {run_dir}")
            continue
        try:
            ev = collect(pcap, proto)
        except utils.TsharkError as e:
            utils.warn(f"tshark failed for {proto}: {e}")
            continue
        if ev:
            epochs = [e["epoch"] for e in ev]
            spans.append((proto, min(epochs), max(epochs)))
        events.extend(ev)

    if spans:
        gmin = min(s[1] for s in spans)
        gmax = max(s[2] for s in spans)
        for proto, lo, hi in spans:
            if lo > gmin + 1.0 or hi < gmax - 1.0:
                utils.warn(
                    f"{proto}.pcap range {utils.epoch_to_iso(lo)}..{utils.epoch_to_iso(hi)} "
                    f"is shorter than the union "
                    f"{utils.epoch_to_iso(gmin)}..{utils.epoch_to_iso(gmax)} — alignment may be partial"
                )

    if args.around is not None:
        half = args.window_ms / 2000.0
        lo, hi = args.around - half, args.around + half
        events = [e for e in events if lo <= e["epoch"] <= hi]

    if args.ue:
        u = args.ue
        # Exact-match against the per-event ue_ids list, plus exact rnti/ueid
        # equality (not substring) for MAC/RLC events whose IDs aren't in ue_ids.
        def _matches(e: dict) -> bool:
            if u in e["ue_ids"]:
                return True
            for tag in ("rnti", "ueid"):
                needle = f"{tag}={u} "
                if needle in e["summary"] + " ":
                    return True
            return False
        events = [e for e in events if _matches(e)]

    events.sort(key=lambda e: e["epoch"])

    if args.json:
        print(json.dumps(events, indent=2))
        return 0

    if not events:
        print("(no events in window)")
        return 0
    for e in events:
        ue_str = ",".join(e["ue_ids"]) if e["ue_ids"] else "-"
        print(f"{e['iso']}  {e['file']:<4}  frame={e['frame']:>6}  "
              f"ue={ue_str:<12}  {e['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
