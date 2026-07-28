#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Resolve and inventory an OCUDU gNB-log input in one shot.

Locates the run directory (a gnb.log file → its parent; a directory containing
gnb.log → itself; a component dir `ocudu-gnb-N-M/` or a Retina `test_gnb[...]`
dir → the latest `YYYY-MM-DD_HH-MM-SS/` subdir that has a gnb.log), confirms the
gnb.log is present and non-empty, lists the analysis artifacts found, and warns
when a test directory holds more than one OCUDU app component (so the caller can
scope to one rather than silently taking the latest). Prints a compact verdict
and exits non-zero if no usable gnb.log can be found.

Unlike pcaps, gNB logs are plain text with nothing to validate — this is
resolution + inventory only, not a format preflight.

Usage:
    resolve.py <path>
    resolve.py <path> --json
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path

import ocudu_log_summary  # reuse resolve_run_dir()

PRIMARY = "gnb.log"
ARTIFACTS = ("gnb.log", "stdout.log", "ocudu_gnb.yml", "metrics.json")
# OCUDU app component directory names that can appear under a test_gnb[...] dir.
COMPONENT_GLOBS = ("ocudu-gnb-*", "ocudu-cu-*", "ocudu-cu-cp-*", "ocudu-cu-up-*", "ocudu-du-*")


def _is_component_name(name: str) -> bool:
    return any(fnmatch.fnmatch(name, g) for g in COMPONENT_GLOBS)


def find_components(root: Path) -> list[str]:
    """Names of distinct OCUDU app components (each holding a gnb.log) under root.

    For every gnb.log beneath `root`, walk up to the nearest component-named
    ancestor; the set of those is what a test directory exposes. Returns [] when
    `root` is at or below a single run/component (no ambiguity to flag).
    """
    comps: set[str] = set()
    for log in root.rglob(PRIMARY):
        if not log.is_file():
            continue
        for anc in log.parents:
            if _is_component_name(anc.name):
                comps.add(anc.name)
                break
            if anc == root:
                break
    return sorted(comps)


def build_report(given: Path) -> dict:
    report: dict = {"input": str(given if not given.exists() else given.resolve())}
    if not given.exists():
        return {**report, "ok": False, "bail": f"not found: {given}"}

    components = find_components(given.resolve()) if given.is_dir() else []

    try:
        run_dir = ocudu_log_summary.resolve_run_dir(str(given))
    except FileNotFoundError as e:
        return {**report, "ok": False, "bail": str(e)}

    report["run_dir"] = str(run_dir)
    primary = run_dir / PRIMARY
    if not primary.is_file():
        return {**report, "ok": False, "bail": f"{PRIMARY} missing in {run_dir}"}
    if primary.stat().st_size == 0:
        return {**report, "ok": False, "bail": f"{PRIMARY} is empty (0 bytes)"}

    report["present"] = [a for a in ARTIFACTS if (run_dir / a).is_file()]
    report["missing"] = [a for a in ARTIFACTS if not (run_dir / a).is_file()]
    if len(components) > 1:
        report["components"] = components
        report["resolved_component"] = next(
            (c for c in components if c in str(run_dir)), None
        )
    report["ok"] = True
    return report


def render_text(r: dict) -> str:
    lines = [f"input:   {r['input']}"]
    if r.get("bail"):
        return "\n".join(lines + [f"verdict: BAIL — {r['bail']}"])
    lines.append(f"run dir: {r['run_dir']}")
    present = ", ".join(r["present"]) if r["present"] else "none"
    line = f"present: {present}"
    if r["missing"]:
        line += f"   (missing: {', '.join(r['missing'])})"
    lines.append(line)
    if r.get("components"):
        rc = r.get("resolved_component") or "the latest"
        lines.append(
            f"NOTE:    {len(r['components'])} OCUDU app components under the input "
            f"({', '.join(r['components'])}); resolved to {rc} — scope to another "
            f"explicitly if you meant a different one."
        )
    lines.append("verdict: OK")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", help="gnb.log, a run dir, a component dir, or a test_gnb[...] dir")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    report = build_report(Path(args.path))
    print(json.dumps({**report, "verdict": "OK" if report.get("ok") else "BAIL"}, indent=2) if args.json else render_text(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
