#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Resolve and preflight a pcap artifact in one shot.

Classifies the path (single pcap / run directory / neither), confirms tshark is
available, and validates each target pcap: non-empty, Wireshark Upper-PDU (DLT
252) framing, and a recognised 3GPP dissector bound on the first frame
(ngap / f1ap / e1ap / mac-nr / rlc-nr). Prints a compact verdict and exits
non-zero if the input cannot be analysed as-is — so the caller can bail.

This replaces the manual "input resolution" + "preflight" steps (realpath/file/
ls, capinfos, and a verbose `tshark -V -c 1` dissector check) with a single
cheap call: one one-frame `frame.protocols` read per pcap.

Usage:
    resolve.py <pcap-or-run-dir>
    resolve.py <pcap-or-run-dir> --json

Exit codes:
    0  - input resolved and every target pcap passed
    1  - input could not be resolved, or a target pcap failed validation
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import utils

# The Upper-PDU dispatcher should bind one of these on the first frame. mac-nr /
# rlc-nr only appear because run_tshark() enables the mac_nr_udp / rlc_nr_udp
# heuristics for every `-r` read (OCUDU wraps those PDUs in a UDP-framed
# Upper-PDU); without them frame.protocols ends in ":data".
KNOWN_DISSECTORS = ("ngap", "f1ap", "e1ap", "mac-nr", "rlc-nr")


def resolve(path: Path) -> dict:
    """Classify the input. Returns a dict with either a `bail` reason or targets.

    Keys: kind, targets (list[Path]), present (list[str]), missing/siblings
    (list[str]), bail (str|None).
    """
    if not path.exists():
        return {"bail": f"not found: {path}"}

    if path.is_dir():
        walk = utils.walk_run_dir(path)  # {stem: Path|None}
        present = [stem for stem, p in walk.items() if p]
        if len(present) < 2:
            found = ", ".join(present) if present else "none"
            return {
                "bail": f"not a run directory (need ≥2 of "
                f"{', '.join(utils.PCAP_NAMES)}); found: {found}"
            }
        missing = [stem for stem, p in walk.items() if not p]
        return {
            "kind": "run directory",
            "targets": [walk[s] for s in present],
            "present": present,
            "missing": missing,
        }

    # A single file.
    sib_walk = utils.walk_run_dir(path.parent)
    siblings = [stem for stem, p in sib_walk.items() if p and p.resolve() != path.resolve()]
    return {
        "kind": "single pcap",
        "targets": [path],
        "siblings": siblings,
    }


def tshark_version() -> str:
    """First line of `tshark -v`. Raises utils.TsharkError if tshark is absent."""
    lines = utils.run_tshark(["-v"])
    return lines[0] if lines else "unknown"


def check_pcap(pcap: Path) -> dict:
    """Validate one pcap. Returns {file, path, ok, ...}."""
    out: dict = {"file": pcap.name, "path": str(pcap)}
    try:
        if pcap.stat().st_size == 0:
            return {**out, "ok": False, "reason": "empty (0 bytes)"}
    except OSError as e:
        return {**out, "ok": False, "reason": f"cannot stat: {e}"}

    try:
        staged = utils.stage_for_tshark(pcap)
        rows = utils.run_tshark(
            ["-r", str(staged), "-c", "1", "-T", "fields", "-e", "frame.protocols"]
        )
    except utils.TsharkError as e:
        return {**out, "ok": False, "reason": f"tshark read failed: {e}"}

    protos = rows[0] if rows else ""
    if not protos:
        return {**out, "ok": False, "reason": "empty (0 frames)"}

    # frame.protocols is the colon-separated dissector chain, e.g.
    # "exported_pdu:ngap" or "exported_pdu:udp:mac-nr:nr-rrc". The 3GPP dissector
    # we care about can sit mid-chain (a MAC PDU carrying RRC continues into
    # nr-rrc), so scan all tokens rather than taking the last one.
    tokens = protos.split(":")
    found = [d for d in KNOWN_DISSECTORS if d in tokens]
    out.update(frame_protocols=protos, dissector=found[0] if found else tokens[-1])
    if "exported_pdu" not in tokens:
        return {**out, "ok": False,
                "reason": f"not Upper-PDU (frame.protocols={protos})"}
    if not found:
        return {**out, "ok": False,
                "reason": f"no 3GPP dissector bound (frame.protocols={protos}); "
                f"try `-d user_dlt 252,...` and note it in references/pcap-format.md"}
    return {**out, "ok": True}


def render_text(report: dict) -> str:
    lines: list[str] = [f"input:  {report['input']}"]
    if report.get("bail") and "kind" not in report:
        lines.append(f"verdict: BAIL — {report['bail']}")
        return "\n".join(lines)

    if report["kind"] == "run directory":
        extra = f"present: {', '.join(report['present'])}"
        if report.get("missing"):
            extra += f"; missing: {', '.join(report['missing'])}"
    else:
        sibs = ", ".join(report["siblings"]) if report.get("siblings") else "none"
        extra = f"siblings present: {sibs}"
    lines.append(f"kind:   {report['kind']}  ({extra})")
    lines.append(f"tshark: {report.get('tshark', 'unavailable')}")

    for f in report.get("files", []):
        if f["ok"]:
            lines.append(f"  {f['file']:<12} OK    Upper-PDU(252)  dissector={f['dissector']}")
        else:
            lines.append(f"  {f['file']:<12} FAIL  {f['reason']}")

    lines.append(f"verdict: {'OK' if report['ok'] else 'BAIL'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", help=".pcap file or a run directory")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    given = Path(args.path)
    report: dict = {"input": str(given if not given.exists() else given.resolve())}

    res = resolve(given)
    if res.get("bail"):
        report.update(bail=res["bail"], ok=False)
        print(json.dumps(report, indent=2) if args.json else render_text(report))
        return 1
    report.update(res)

    try:
        report["tshark"] = tshark_version()
    except utils.TsharkError as e:
        report.update(ok=False, bail=str(e), files=[])
        print(json.dumps(report, indent=2) if args.json else render_text(report))
        return 1

    files = [check_pcap(t) for t in res["targets"]]
    # `targets` are Paths; drop them from the JSON payload in favour of `files`.
    report.pop("targets", None)
    report["files"] = files
    report["ok"] = all(f["ok"] for f in files)

    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
