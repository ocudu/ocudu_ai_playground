#!/usr/bin/env python3
"""One-shot summary for an OCUDU run directory.

Calls pcap_overview.py, then the three per-protocol UE-ID scripts for whichever
sibling pcaps are present, and prints a unified summary block. Equivalent to
running pcap_overview + f1ap_ue_ids + ngap_ue_ids + e1ap_ue_ids by hand.

Usage:
    summary.py <run-dir>
    summary.py <run-dir> --top 5
    summary.py <run-dir> --ue-limit 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import utils
import pcap_overview
import f1ap_ue_ids
import ngap_ue_ids
import e1ap_ue_ids


def _section(title: str) -> None:
    print(f"\n## {title}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", help="OCUDU run directory containing sibling pcaps")
    ap.add_argument("--top", type=int, default=5,
                    help="top N procedure codes per pcap (pcap_overview)")
    ap.add_argument("--ue-limit", type=int, default=20,
                    help="cap UE-ID rows per protocol (default 20; use 0 for no cap)")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not utils.is_run_dir(run_dir):
        print(f"error: not a run directory (need ≥2 of {utils.PCAP_NAMES}): {run_dir}",
              file=sys.stderr)
        return 1

    sibs = utils.walk_run_dir(run_dir)

    _section("pcap overview")
    rc = pcap_overview.main([str(run_dir), "--top", str(args.top)])
    if rc != 0:
        return rc

    for proto, mod, helper in (
        ("F1AP", f1ap_ue_ids, sibs["f1ap"]),
        ("NGAP", ngap_ue_ids, sibs["ngap"]),
        ("E1AP", e1ap_ue_ids, sibs["e1ap"]),
    ):
        if helper is None:
            continue
        _section(f"{proto} UEs")
        mod.main([str(helper), "--limit", str(args.ue_limit)])

    return 0


if __name__ == "__main__":
    sys.exit(main())
