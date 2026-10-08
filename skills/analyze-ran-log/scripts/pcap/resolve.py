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
from parsers.pcap import run

# Where to record a dissector binding that tshark does not apply on its own.
_DISSECTOR_HINT = "; try `-d user_dlt 252,...` and note it in references/pcap/reference/pcap-format.md"


def check_pcap(pcap: Path) -> dict:
    out = run.check_pcap(utils.TSHARK, pcap)
    if not out["ok"] and out["reason"].startswith("no 3GPP dissector bound"):
        out["reason"] += _DISSECTOR_HINT
    return out


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


def _print(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps({**report, "verdict": "OK" if report.get("ok") else "BAIL"}, indent=2))
    else:
        print(render_text(report))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", help=".pcap file or a run directory")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    given = Path(args.path)
    report: dict = {"input": str(given if not given.exists() else given.resolve())}

    res = run.resolve(given)
    if res.get("bail"):
        report.update(bail=res["bail"], ok=False)
        _print(report, args.json)
        return 1
    report.update(res)

    try:
        report["tshark"] = utils.TSHARK.version()
    except utils.TsharkError as e:
        report.update(ok=False, bail=str(e), files=[])
        _print(report, args.json)
        return 1

    files = [check_pcap(t) for t in res["targets"]]
    # Paths are not JSON serializable, and "files" describes the same pcaps.
    report.pop("targets", None)
    report["files"] = files
    report["ok"] = all(f["ok"] for f in files)
    _print(report, args.json)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
