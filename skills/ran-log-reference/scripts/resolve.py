#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Classify a RAN test artifact and delegate to its per-type resolve/preflight.

This is the single entrypoint for the ran-log-reference skill. It classifies
the input into a kind and then runs that kind's resolve script as a subprocess,
so each per-type script keeps its own directory on sys.path for its sibling
imports (e.g. resolve.py importing ocudu_log_summary):

    kind        marker                                  delegate
    ----------  --------------------------------------  ----------------------------
    pcap        *.pcap/*.pcapng, or a dir of them       scripts/pcap/resolve.py
    ocudu       gnb.log / OCUDU component or run        scripts/ocudu/resolve.py
    amari-ue    ue.log / Amarisoft UE component/run     scripts/amari-ue/resolve.py
    correlate   a run dir spanning ≥2 RAN components     scripts/correlate/resolve.py

The kind line and a `-> read references/<type>/` pointer are printed first, then
the delegate's own output (inventory/validation + its `verdict:` line). The exit
code is the delegate's. A whole `test_gnb[...]` run that spans several RAN
application components (gNB + UE + 5GC) resolves to `correlate` for cross-artifact
work; a single artifact or single-component dir resolves to its own type. Pass
`--type` to force a kind.

Usage:
    resolve.py <artifact-or-dir> [--type pcap|ocudu|amari-ue|correlate] [passthrough args...]
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# kind -> (subdir, script) it delegates to.
DELEGATE = {
    "pcap": ("pcap", "resolve.py"),
    "ocudu": ("ocudu", "resolve.py"),
    "amari-ue": ("amari-ue", "resolve.py"),
    "correlate": ("correlate", "resolve.py"),
}
KINDS = tuple(DELEGATE)

PCAP_NAMES = ("mac.pcap", "rlc.pcap", "f1ap.pcap", "e1ap.pcap", "ngap.pcap")
# OCUDU app log basenames that mark an ocudu artifact.
GNB_LOGS = ("gnb.log", "du.log", "cu.log", "cu_cp.log", "cu_up.log")
UE_LOG = "ue.log"
# 5GC/MME log basenames (Amarisoft core).
CORE_LOGS = ("mme.log", "amf.log")


def _has_under(root: Path, name: str) -> bool:
    """True if `name` exists at `root` or anywhere beneath it (bounded by first hit)."""
    if (root / name).is_file():
        return True
    return next(root.rglob(name), None) is not None


def _has_any_under(root: Path, names) -> bool:
    return any(_has_under(root, n) for n in names)


def classify(path: Path) -> tuple[str | None, str]:
    """Return (kind, reason). kind is None when the input is ambiguous/unknown."""
    if path.is_file():
        suf = path.suffix.lower()
        if suf in (".pcap", ".pcapng"):
            return "pcap", f"{path.name} is a packet capture"
        if path.name == UE_LOG:
            return "amari-ue", "ue.log is an Amarisoft UE log"
        if path.name in GNB_LOGS:
            return "ocudu", f"{path.name} is an OCUDU app log"
        return None, f"unrecognized file: {path.name}"

    if not path.is_dir():
        return None, f"not a file or directory: {path}"

    # A directory that directly holds the primary log is unambiguous — point at it.
    if any((path / n).is_file() for n in GNB_LOGS):
        return "ocudu", "directory contains an OCUDU app log"
    if (path / UE_LOG).is_file():
        return "amari-ue", "directory contains ue.log"
    if sum((path / n).is_file() for n in PCAP_NAMES) >= 1:
        return "pcap", "directory contains Upper-PDU pcaps"

    # Component / test directory: detect by what lives beneath it.
    has_gnb = _has_any_under(path, GNB_LOGS)
    has_ue = _has_under(path, UE_LOG)
    has_core = _has_any_under(path, CORE_LOGS)
    has_pcap = _has_any_under(path, PCAP_NAMES)
    # A directory spanning ≥2 RAN application components (gNB / UE / 5GC) is a
    # whole-run directory → cross-artifact correlation.
    apps = [("OCUDU app", has_gnb), ("Amarisoft UE", has_ue), ("5GC", has_core)]
    present = [name for name, ok in apps if ok]
    if len(present) >= 2:
        return "correlate", f"directory spans multiple RAN components ({', '.join(present)})"
    if has_gnb:
        return "ocudu", "OCUDU app log found below the directory"
    if has_ue:
        return "amari-ue", "ue.log found below the directory"
    if has_pcap:
        return "pcap", "Upper-PDU pcaps found below the directory"
    return None, "no gnb.log / ue.log / *.pcap found"


def main(argv: list[str]) -> int:
    args = argv[1:]
    forced: str | None = None
    if "--type" in args:
        i = args.index("--type")
        try:
            forced = args[i + 1]
        except IndexError:
            print("error: --type requires a value", file=sys.stderr)
            return 2
        if forced not in KINDS:
            print(f"error: --type must be one of {', '.join(KINDS)}", file=sys.stderr)
            return 2
        del args[i : i + 2]

    if not args:
        print(
            "usage: resolve.py <artifact-or-dir> "
            "[--type pcap|ocudu|amari-ue|correlate] [passthrough args...]",
            file=sys.stderr,
        )
        return 2

    target = Path(args[0]).expanduser()
    passthrough = args[1:]

    if forced:
        kind, reason = forced, "forced via --type"
    else:
        kind, reason = classify(target)

    if kind is None:
        print(f"kind: UNKNOWN ({reason})")
        print("verdict: BAIL")
        return 1

    print(f"kind: {kind} ({reason})")
    print(f"-> read references/{kind}/")
    if kind == "correlate":
        # The correlate subtree has no conventions.md; point at its entry doc.
        print("-> start at: references/correlate/cross-correlation.md")
    else:
        print(f"-> conventions: references/{kind}/conventions.md")
    print()
    sys.stdout.flush()  # ensure the headline precedes the delegate's output when piped

    subdir, script = DELEGATE[kind]
    delegate = SCRIPT_DIR / subdir / script
    if not delegate.is_file():
        print(f"error: delegate script missing: {delegate}", file=sys.stderr)
        print("verdict: BAIL")
        return 1

    proc = subprocess.run(
        [sys.executable, str(delegate), str(target), *passthrough],
        check=False,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
