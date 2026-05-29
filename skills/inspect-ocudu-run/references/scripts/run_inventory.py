#!/usr/bin/env python3
"""
run_inventory.py — Inventory an OCUDU Retina test/run directory.

Enumerates the components of a `test_gnb[...]` directory (OCUDU gNB/DU/CU,
Amarisoft UE, Amarisoft 5GC), resolves each component's latest run subdir,
lists the artifacts present, maps each to the sub-skill that analyses it,
parses testbed.json (component -> IP:port), and reports the per-source clock
anchors needed for cross-correlation. This is the dispatch backbone for all
three modes of the inspect-ocudu-run skill.

Usage:
    python3 run_inventory.py <test-dir | component-dir | run-dir> [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import utils

# Component dir prefix -> (role, sub-skill that owns its primary log).
COMPONENT_ROLES = [
    ("ocudu-cu-cp", "cu-cp", "analyze-ocudu-gnb-log"),
    ("ocudu-cu-up", "cu-up", "analyze-ocudu-gnb-log"),
    ("ocudu-cu", "cu", "analyze-ocudu-gnb-log"),
    ("ocudu-du", "du", "analyze-ocudu-gnb-log"),
    ("ocudu-gnb", "gnb", "analyze-ocudu-gnb-log"),
    ("ocudu-odu", "odu", "analyze-ocudu-gnb-log"),
    ("ocudu-ocu", "ocu", "analyze-ocudu-gnb-log"),
    ("amarisoft-ue", "ue", "analyze-amari-ue-log"),
    ("amarisoft-5gc", "5gc", "(light-touch; future analyze-amari-5gc-log)"),
    ("amarisoft-mme", "5gc", "(light-touch; future analyze-amari-5gc-log)"),
]

RUN_SUBDIR_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")

# Primary OCUDU app-log filenames, in preference order.
OCUDU_LOG_NAMES = ("gnb.log", "du.log", "cu.log", "cu_cp.log", "cu_up.log")
PCAP_NAMES = ("ngap.pcap", "f1ap.pcap", "e1ap.pcap", "mac.pcap", "rlc.pcap")


def classify(component_dir_name: str):
    for prefix, role, subskill in COMPONENT_ROLES:
        if component_dir_name.startswith(prefix):
            return role, subskill
    return None, None


def latest_run_subdir(component_dir: Path) -> Path:
    """Return the latest YYYY-MM-DD_HH-MM-SS subdir, or the component dir itself if flat."""
    subs = sorted(
        (d for d in component_dir.iterdir() if d.is_dir() and RUN_SUBDIR_RE.match(d.name)),
        key=lambda d: d.name,
    )
    return subs[-1] if subs else component_dir


def resolve_test_dir(path: Path) -> tuple[Path, list[Path]]:
    """Return (test_dir, component_dirs). Accepts a test dir, a component dir, or a run dir."""
    path = path.resolve()

    def component_children(d: Path) -> list[Path]:
        return sorted(
            c for c in d.iterdir()
            if c.is_dir() and classify(c.name)[0] is not None
        )

    if path.is_dir():
        comps = component_children(path)
        if comps:
            return path, comps
        # A component dir given directly: report the parent as the test dir but
        # scope to just this component (we don't pull in sibling components when
        # the user pointed at one specifically).
        if classify(path.name)[0] is not None and path.parent.is_dir():
            return path.parent, [path]
        # A run subdir inside a component dir?
        if RUN_SUBDIR_RE.match(path.name) and classify(path.parent.name)[0] is not None:
            return path.parent.parent, [path.parent]
    raise SystemExit(f"error: no OCUDU components found under {path}")


def inventory_component(comp_dir: Path) -> dict:
    role, subskill = classify(comp_dir.name)
    run_dir = latest_run_subdir(comp_dir)
    info: dict = {
        "component": comp_dir.name,
        "role": role,
        "subskill": subskill,
        "run_dir": str(run_dir),
        "logs": [],
        "pcaps": [],
        "configs": [],
        "metrics": False,
        "clock_anchor": None,
    }

    # OCUDU app log
    if role in ("gnb", "du", "cu", "cu-cp", "cu-up", "odu", "ocu"):
        for name in OCUDU_LOG_NAMES:
            f = run_dir / name
            if f.is_file():
                info["logs"].append(name)
        primary = next((run_dir / n for n in OCUDU_LOG_NAMES if (run_dir / n).is_file()), None)
        if primary:
            info["clock_anchor"] = {"type": "gnb-utc", "first_event": utils.first_gnb_event_ts(primary)}
        for y in ("ocudu_gnb.yml", "ocudu_du.yml", "ocudu_cu.yml"):
            if (run_dir / y).is_file():
                info["configs"].append(y)
        for p in PCAP_NAMES:
            if (run_dir / p).is_file():
                info["pcaps"].append(p)
    elif role == "ue":
        if (run_dir / "ue.log").is_file():
            info["logs"].append("ue.log")
            info["clock_anchor"] = {"type": "amari-utc",
                                    "started_on": utils.started_on_date(run_dir / "ue.log")}
        if (run_dir / "amarisoft_ue.cfg").is_file():
            info["configs"].append("amarisoft_ue.cfg")
    elif role == "5gc":
        for name in ("mme.log", "amf.log", "open5gs.log"):
            if (run_dir / name).is_file():
                info["logs"].append(name)
        if info["logs"]:
            info["clock_anchor"] = {"type": "amari-utc",
                                    "started_on": utils.started_on_date(run_dir / info["logs"][0])}
        for c in ("amarisoft_mme.cfg", "amarisoft_amf.cfg"):
            if (run_dir / c).is_file():
                info["configs"].append(c)

    if (run_dir / "metrics.json").is_file():
        info["metrics"] = True
    return info


def build_inventory(path_str: str) -> dict:
    test_dir, comp_dirs = resolve_test_dir(Path(path_str))
    comps = [inventory_component(c) for c in comp_dirs]
    testbed = {}
    tb = test_dir / "testbed.json"
    if tb.is_file():
        testbed = utils.parse_testbed(tb)
    return {"test_dir": str(test_dir), "testbed": testbed, "components": comps}


def render_text(inv: dict) -> str:
    lines = [f"Test directory : {inv['test_dir']}", ""]
    lines.append("Components:")
    for c in inv["components"]:
        lines.append(f"  [{c['role']}] {c['component']}  (sub-skill: {c['subskill']})")
        rd = Path(c["run_dir"]).name
        lines.append(f"        run subdir : {rd}")
        if c["logs"]:
            lines.append(f"        logs       : {', '.join(c['logs'])}")
        if c["configs"]:
            lines.append(f"        configs    : {', '.join(c['configs'])}")
        if c["pcaps"]:
            lines.append(f"        pcaps      : {', '.join(c['pcaps'])}  (sub-skill: analyze-pcap)")
        if c["metrics"]:
            lines.append("        metrics    : metrics.json")
        ca = c["clock_anchor"]
        if ca and ca.get("type") == "gnb-utc" and ca.get("first_event"):
            lines.append(f"        clock      : first event {ca['first_event']} (UTC)")
        elif ca and ca.get("type") == "amari-utc" and ca.get("started_on"):
            lines.append(f"        clock      : # Started on {ca['started_on']} (UTC)")
    if inv["testbed"]:
        lines.append("")
        lines.append("Testbed map (component -> address:port):")
        # Collapse large families of identical-prefix components (e.g. 64 UEs)
        # into one range line to keep the output token-cheap.
        ue_items = [(n, ni) for n, ni in inv["testbed"].items() if n.startswith("amarisoft-ue-")]
        other = [(n, ni) for n, ni in inv["testbed"].items() if not n.startswith("amarisoft-ue-")]
        for name, ni in other:
            lines.append(f"  {name:<22} {ni['address']}:{ni['port']}")
        if ue_items:
            ports = sorted(ni["port"] for _, ni in ue_items)
            addr = ue_items[0][1]["address"]
            if len(ue_items) == 1:
                n, ni = ue_items[0]
                lines.append(f"  {n:<22} {ni['address']}:{ni['port']}")
            else:
                lines.append(f"  amarisoft-ue-1..{len(ue_items):<10} {addr}:{ports[0]}-{ports[-1]} "
                             f"({len(ue_items)} UEs)")
    lines.append("")
    lines.append("Clock note: all logs (gnb/ue/mme) and pcap frame.time_epoch are UTC and")
    lines.append("directly comparable. capinfos/tshark DISPLAY in local TZ — use raw")
    lines.append("frame.time_epoch. PHY (SFN.slot, RNTI) is the exact cross-source radio key.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="test dir, component dir, or run dir")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    if not Path(args.path).exists():
        print(f"error: not found: {args.path}", file=sys.stderr)
        return 1

    inv = build_inventory(args.path)
    print(json.dumps(inv, indent=2) if args.json else render_text(inv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
