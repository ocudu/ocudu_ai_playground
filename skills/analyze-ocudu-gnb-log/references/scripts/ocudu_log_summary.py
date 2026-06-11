#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
ocudu_log_summary.py — Summarize an OCUDU gNB run directory.

Single-pass parse of gnb.log + stdout.log + ocudu_gnb.yml + metrics.json.
Emits a compact, token-efficient summary suitable for AI context.

Usage:
  python3 ocudu_log_summary.py <path>

<path> can be:
  - gnb.log file directly
  - Run directory containing gnb.log (e.g. 2026-05-18_18-18-27/)
  - Component directory ocudu-gnb-N-M/ (finds latest timestamp subdirectory)
  - Retina test directory test_gnb[...] (finds latest ocudu-gnb-N-M/ subdir)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def resolve_run_dir(path_str: str) -> Path:
    p = Path(path_str).resolve()

    if p.is_file():
        return p.parent

    if (p / "gnb.log").exists():
        return p

    # Component dir or test dir: locate gnb.log under it; prefer the latest by sort.
    candidates = sorted(
        [d for d in p.rglob("gnb.log") if d.is_file()],
        key=lambda f: str(f),
    )
    if candidates:
        return candidates[-1].parent

    raise FileNotFoundError(f"No gnb.log found under {p}")


# ---------------------------------------------------------------------------
# ocudu_gnb.yml parser
# ---------------------------------------------------------------------------

# The YAML file is a concatenation of multiple documents without `---`. We do
# not use a YAML library because duplicate keys would collapse silently. We
# only need a handful of values, so a top-to-bottom scan that records the last
# occurrence of each interesting key is enough.

CFG_KEYS = (
    "gnb_id", "ran_node_name",
    "all_level", "lib_level", "rrc_level", "ngap_level", "f1ap_level",
    "e1ap_level", "pdcp_level", "mac_level", "phy_level", "sec_level",
    "cu_level", "xnap_level", "rlc_level",
    "config_level", "hex_max_size",
    "pci", "band", "dl_arfcn", "channel_bandwidth_MHz", "common_scs",
    "nof_antennas_dl", "nof_antennas_ul",
    "srate", "device_driver", "sync", "time_alignment_calibration",
    "enable_log", "enable_json", "autostart_stdout_metrics",
    "rlc_enable", "ngap_enable", "f1ap_enable", "e1ap_enable", "mac_enable",
)


def parse_cfg(cfg_path: Path) -> dict:
    result: dict = {
        "raw": {},
        "pcaps": [],
        "log_levels": {},
        "tdd": False,
        "amf_addrs": [],
        "amf_port": None,
        "amf_bind_addrs": [],
    }
    if not cfg_path.exists():
        return result

    text = cfg_path.read_text(errors="replace")

    # Last-wins for each simple scalar key.
    for key in CFG_KEYS:
        for m in re.finditer(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*(?:#.*)?$",
                             text, flags=re.MULTILINE):
            result["raw"][key] = m.group(1).strip().strip('"')

    # PCAPs: any `<name>_enable: true` in pcap context
    for m in re.finditer(r"^\s*(\w+)_enable\s*:\s*true\s*$", text, flags=re.MULTILINE):
        proto = m.group(1)
        if proto in {"ngap", "f1ap", "e1ap", "mac", "rlc", "n3", "f1u", "xnap",
                     "e2ap_cu_cp", "e2ap_cu_up", "e2ap_du"}:
            result["pcaps"].append(proto)

    # Per-layer log levels — keep only ones explicitly set. cu_level gates the
    # CU-CP/CU-UP layers (UE creates, bearers, Initial Context Setup), so it must
    # be shown to explain why those procedure counts may be zero.
    for lvl in ("all_level", "lib_level", "rrc_level", "ngap_level",
                "f1ap_level", "e1ap_level", "cu_level", "pdcp_level", "mac_level",
                "phy_level", "sec_level", "xnap_level", "rlc_level", "config_level"):
        if lvl in result["raw"]:
            result["log_levels"][lvl.removesuffix("_level")] = result["raw"][lvl]

    if "tdd_ul_dl_cfg" in text or re.search(r"^\s*duplex\s*:\s*tdd\b", text, flags=re.MULTILINE):
        result["tdd"] = True

    # AMF block — addrs/port/bind_addrs may live under cu_cp.amf
    for m in re.finditer(r"^\s+addrs\s*:\s*(.+?)\s*$", text, flags=re.MULTILINE):
        v = m.group(1).strip().strip('"')
        if re.match(r"\d+\.\d+\.\d+\.\d+", v):
            result["amf_addrs"].append(v)
    for m in re.finditer(r"^\s+bind_addrs\s*:\s*(.+?)\s*$", text, flags=re.MULTILINE):
        v = m.group(1).strip().strip('"')
        if re.match(r"\d+\.\d+\.\d+\.\d+", v):
            result["amf_bind_addrs"].append(v)
    m = re.search(r"^\s+port\s*:\s*(\d+)\s*$", text, flags=re.MULTILINE)
    if m:
        result["amf_port"] = int(m.group(1))

    return result


# ---------------------------------------------------------------------------
# gnb.log parser
# ---------------------------------------------------------------------------

# Real event lines start with an ISO-8601 timestamp. Bodies of the CONFIG echo
# at the top of the file (which has no per-line timestamp) are skipped by this
# anchor.
LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6})\s+"
    r"\[(?P<layer>[A-Z][A-Z0-9_ -]*?)\s*\]\s+"
    r"\[(?P<lvl>[A-Z])\]\s+"
    r"(?P<msg>.*)$"
)

UE_RE = re.compile(r"\bue=(\d+)\b")
PCI_RE = re.compile(r"\bpci=(\d+)\b")
CRNTI_RE = re.compile(r"c-rnti=0x([0-9a-fA-F]+)")

# Warnings that are expected in healthy OCUDU runs and should not be flagged as
# anomalies. The per-UE creation-latency lines are performance instrumentation,
# not faults; the DRM/hyperthreading lines are host-environment notes.
BENIGN_WARNING_SUBSTRINGS = (
    "DRM KMS polling is enabled",
    "hyperthreading",
    "UE creation (ue=",        # [SCHED] perf instrumentation
    "MAC UE creation (ue=",    # [MAC]  perf instrumentation
)


def _is_benign_warning(msg: str) -> bool:
    return any(s in msg for s in BENIGN_WARNING_SUBSTRINGS)


def parse_gnb_log(gnb_log: Path) -> dict:
    result = {
        "build_commit": None,
        "build_branch": None,
        "first_ts": None,
        "last_ts": None,
        "clean_shutdown": False,
        "ng_setup": None,            # 'success' | 'failure' | None
        "amf_connected_ts": None,
        "cells_created": [],         # [(ts, pci)]
        "ue_creates": [],            # [(ts, ue, c-rnti)]
        "ue_releases": [],           # [(ts, ue)]
        "init_ctx_done": [],         # [(ts, ue)]
        "rrc_reconfigs": 0,
        "ho_count": 0,               # reconfigurationWithSync occurrences (multi-line body)
        "ngap_handover_count": 0,    # NGAP HandoverRequired / HandoverRequest etc.
        "reest_count": 0,            # rrcReestablishmentRequest
        "bearer_setups": 0,
        "bearer_modifications": 0,
        "bearer_releases": 0,
        "prach_events": 0,
        "crc_fails": 0,
        "warnings": [],              # non-benign W lines: (ts, layer, msg), capped
        "benign_warning_count": 0,   # expected perf/host warnings, not anomalies
        "errors": [],                # E/C lines: (ts, layer, msg), capped
        "ues_seen": set(),
        "rntis_seen": set(),
        "pcis_seen": set(),
        "rrc_msgs": [],              # [(ts, layer, msg)] - sampled key RRC lines
        "metrics_rows": 0,
        "last_metrics": None,        # the last [METRICS] line text
        "shutdown_signal_ts": None,
    }

    if not gnb_log.exists():
        return result

    # We tolerate the giant CONFIG echo cheaply by not invoking the regex until
    # we see a leading digit (ISO timestamp). Body lines of the echo start with
    # letters/colons.
    with open(gnb_log, encoding="utf-8", errors="replace") as f:
        for raw in f:
            if not raw or raw[0] not in "0123456789":
                continue
            m = LINE_RE.match(raw)
            if not m:
                continue

            ts = m.group("ts")
            layer = m.group("layer").strip()
            lvl = m.group("lvl")
            msg = m.group("msg")

            if result["first_ts"] is None:
                result["first_ts"] = ts
            result["last_ts"] = ts

            # Warnings / errors / critical
            if lvl in ("E", "C"):
                if len(result["errors"]) < 50:
                    result["errors"].append((ts, layer, msg.strip()))
            elif lvl == "W":
                if _is_benign_warning(msg):
                    result["benign_warning_count"] += 1
                elif len(result["warnings"]) < 50:
                    result["warnings"].append((ts, layer, msg.strip()))

            # Build identity (top of file)
            if layer == "GNB" and "Built in" in msg:
                bm = re.search(r"commit (\S+) on branch (\S+)", msg)
                if bm:
                    result["build_commit"] = bm.group(1)
                    result["build_branch"] = bm.group(2)

            # NGAP NG setup
            if layer == "NGAP":
                if "NGSetupResponse" in msg:
                    result["ng_setup"] = "success"
                elif "NGSetupFailure" in msg:
                    result["ng_setup"] = "failure"
                if "HandoverRequired" in msg or "HandoverRequest" in msg:
                    result["ngap_handover_count"] += 1

            # AMF connection up
            if layer == "CU-CP" and "Connection to AMF" in msg and "established" in msg:
                result["amf_connected_ts"] = ts

            # Cell creation (SCHED side, deterministic single line)
            if layer == "SCHED" and "Cell creation idx=" in msg:
                pci_m = PCI_RE.search(msg)
                if pci_m:
                    pci = int(pci_m.group(1))
                    result["cells_created"].append((ts, pci))
                    result["pcis_seen"].add(pci)

            # PRACH (SCHED side: "prach(ra-rnti=...)")
            if layer == "SCHED" and "prach(" in msg:
                result["prach_events"] += 1

            # PHY CRC failures
            if layer == "PHY" and "crc=KO" in msg:
                result["crc_fails"] += 1

            # UE creation (CU-CP)
            if layer == "CU-CP" and ": UE created" in msg:
                ue_m = UE_RE.search(msg)
                rn_m = CRNTI_RE.search(msg)
                ue = ue_m.group(1) if ue_m else "?"
                rnti = rn_m.group(1) if rn_m else "?"
                result["ue_creates"].append((ts, ue, rnti))
                result["ues_seen"].add(ue)
                if rnti != "?":
                    result["rntis_seen"].add(rnti)

            # Initial Context Setup outcome
            if layer == "CU-CP" and '"Initial Context Setup Routine" finished successfully' in msg:
                ue_m = UE_RE.search(msg)
                result["init_ctx_done"].append((ts, ue_m.group(1) if ue_m else "?"))

            # UE Removal Routine
            if layer == "CU-CP" and '"UE Removal Routine" finished successfully' in msg:
                ue_m = UE_RE.search(msg)
                result["ue_releases"].append((ts, ue_m.group(1) if ue_m else "?"))

            # RRC counters and sampled events
            if layer == "RRC":
                if "rrcReconfiguration" in msg and "Complete" not in msg:
                    result["rrc_reconfigs"] += 1
                if "rrcReestablishmentRequest" in msg or "reestablishmentRequest" in msg:
                    result["reest_count"] += 1
                # Keep a small set of key RRC lines for the timeline.
                if any(k in msg for k in (
                    "rrcSetup", "rrcReconfiguration", "securityModeCommand",
                    "securityModeComplete", "rrcRelease", "rrcReestablishment",
                    "rrcReject",
                )):
                    if len(result["rrc_msgs"]) < 200:
                        result["rrc_msgs"].append((ts, layer, msg.strip()))

            # Handover bodies appear as multi-line continuation under RRC
            # reconfiguration; the canonical marker is the ASN.1 brace.
            if "reconfigurationWithSync" in msg and "{" in msg:
                result["ho_count"] += 1

            # E1AP bearer lifecycle. Each procedure is logged on both CU-CP and
            # CU-UP sides; count from CU-CP only to avoid double-counting.
            if layer == "CU-CP-E1":
                if "BearerContextSetupResponse" in msg:
                    result["bearer_setups"] += 1
                elif "BearerContextModificationResponse" in msg:
                    result["bearer_modifications"] += 1
                elif "BearerContextReleaseComplete" in msg:
                    result["bearer_releases"] += 1

            # Scheduler metrics rows
            if layer == "METRICS":
                result["metrics_rows"] += 1
                result["last_metrics"] = msg

            # Shutdown markers
            if "Closing PCAP files" in msg and result["shutdown_signal_ts"] is None:
                result["shutdown_signal_ts"] = ts
            if "Workers stopped successfully" in msg:
                result["clean_shutdown"] = True

    result["ues_seen"] = sorted(result["ues_seen"], key=lambda s: int(s) if s.isdigit() else -1)
    result["rntis_seen"] = sorted(result["rntis_seen"])
    result["pcis_seen"] = sorted(result["pcis_seen"])
    return result


# ---------------------------------------------------------------------------
# stdout.log parser
# ---------------------------------------------------------------------------

def parse_stdout(stdout_log: Path) -> dict:
    result = {
        "banner_commit": None,
        "cells": [],            # raw "Cell pci=..." lines
        "amf_connected": False,
        "started": False,
        "stopped": False,
        "logfile_path": None,
        "metrics_rows": 0,
    }
    if not stdout_log.exists():
        return result

    in_table = False
    with open(stdout_log, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped:
                continue

            if "OCUDU gNB (commit" in stripped:
                m = re.search(r"commit ([0-9a-fA-F]+)", stripped)
                if m:
                    result["banner_commit"] = m.group(1)
            elif stripped.startswith("Cell pci="):
                result["cells"].append(stripped)
            elif stripped.startswith("N2:") and "completed" in stripped:
                result["amf_connected"] = True
            elif stripped.startswith("==== gNB started ==="):
                result["started"] = True
            elif stripped.startswith("Stopping..."):
                result["stopped"] = True
            elif stripped.startswith("Logfile stored in"):
                m = re.search(r"Logfile stored in (\S+)", stripped)
                if m:
                    result["logfile_path"] = m.group(1)
            elif re.match(r"^\s*\d+\s+[0-9a-f]{4}\s+\|", line):
                in_table = True
                result["metrics_rows"] += 1
            elif in_table and not line.lstrip().startswith("pci") and not line.lstrip().startswith("|"):
                in_table = False

    return result


# ---------------------------------------------------------------------------
# metrics.json parser
# ---------------------------------------------------------------------------

def _load_metrics_records(metrics_path: Path) -> list:
    """Return the list of metric records from metrics.json.

    The file is a standard JSON array (`[ {...}, {...} ]`). Parse it whole.
    Fall back to lenient line-by-line parsing only if the array is malformed
    (e.g. a run that was killed mid-write leaves an unclosed array).
    """
    text = metrics_path.read_text(errors="replace").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        pass
    # Salvage path: strip a leading "[" / trailing "]" and parse each comma-
    # terminated record independently so a truncated tail doesn't lose the rest.
    records = []
    for line in text.lstrip("[").rstrip("]").splitlines():
        line = line.strip().rstrip(",")
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def parse_metrics(metrics_path: Path) -> dict:
    result = {
        "records": 0,
        "peak_dl_brate": 0.0,
        "peak_ul_brate": 0.0,
        "max_latency_us": 0.0,
        "late_dl_harqs": 0,
        "late_ul_harqs": 0,
        "failed_pdcch": 0,
        "failed_uci": 0,
        "errors": 0,
        "msg3_ok": 0,
        "msg3_nok": 0,
        "event_counts": Counter(),
    }
    if not metrics_path.exists():
        return result

    records = _load_metrics_records(metrics_path)
    for obj in records:
        result["records"] += 1
        cells = obj.get("cells") or []
        for cell in cells:
            cm = cell.get("cell_metrics", {})
            result["late_dl_harqs"] += cm.get("late_dl_harqs", 0) or 0
            result["late_ul_harqs"] += cm.get("late_ul_harqs", 0) or 0
            result["failed_pdcch"] += cm.get("nof_failed_pdcch_allocs", 0) or 0
            result["failed_uci"] += cm.get("nof_failed_uci_allocs", 0) or 0
            result["errors"] += cm.get("error_indication_count", 0) or 0
            # Msg3 (RACH 3rd message) decode outcomes — high nok = RACH contention.
            result["msg3_ok"] += cm.get("msg3_nof_ok", 0) or 0
            result["msg3_nok"] += cm.get("msg3_nof_nok", 0) or 0
            for ue in cell.get("ue_list", []) or []:
                dl = ue.get("dl_brate", 0) or 0
                ul = ue.get("ul_brate", 0) or 0
                if dl > result["peak_dl_brate"]:
                    result["peak_dl_brate"] = dl
                if ul > result["peak_ul_brate"]:
                    result["peak_ul_brate"] = ul
            mlu = cm.get("max_latency", 0) or 0
            if mlu > result["max_latency_us"]:
                result["max_latency_us"] = mlu
            for ev in cell.get("event_list", []) or []:
                t = ev.get("event_type")
                if t:
                    result["event_counts"][t] += 1
    return result


# ---------------------------------------------------------------------------
# Duration helper
# ---------------------------------------------------------------------------

def ts_delta_seconds(t1: str, t2: str) -> float | None:
    """Compute seconds between two ISO-8601 timestamps with microsecond precision."""
    try:
        def to_sec(t):
            date, tod = t.split("T")
            h, m, s = tod.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        return to_sec(t2) - to_sec(t1)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def summarize(path_str: str) -> None:
    run_dir = resolve_run_dir(path_str)
    gnb_log = run_dir / "gnb.log"
    stdout_log = run_dir / "stdout.log"
    cfg_path = run_dir / "ocudu_gnb.yml"
    metrics_path = run_dir / "metrics.json"

    print(f"Run directory : {run_dir}")
    print()

    cfg = parse_cfg(cfg_path)
    log = parse_gnb_log(gnb_log)
    out = parse_stdout(stdout_log)
    met = parse_metrics(metrics_path)

    # ----- Build -----
    print("=== Build ===")
    if log["build_commit"]:
        print(f"  Commit / branch : {log['build_commit']} / {log['build_branch']}")
    if out["banner_commit"] and out["banner_commit"] != log["build_commit"]:
        print(f"  stdout banner   : {out['banner_commit']}")
    print()

    # ----- Configuration -----
    print("=== Configuration ===")
    raw = cfg["raw"]
    if "gnb_id" in raw:
        print(f"  gnb_id        : {raw['gnb_id']}")
    if "ran_node_name" in raw:
        print(f"  ran_node_name : {raw['ran_node_name']}")
    cell_bits = []
    if "pci" in raw:
        cell_bits.append(f"pci={raw['pci']}")
    if "band" in raw:
        cell_bits.append(f"band=n{raw['band']}")
    if "channel_bandwidth_MHz" in raw:
        cell_bits.append(f"bw={raw['channel_bandwidth_MHz']} MHz")
    if "common_scs" in raw:
        cell_bits.append(f"scs={raw['common_scs']} kHz")
    if "dl_arfcn" in raw:
        cell_bits.append(f"dl_arfcn={raw['dl_arfcn']}")
    if "nof_antennas_dl" in raw and "nof_antennas_ul" in raw:
        cell_bits.append(f"{raw['nof_antennas_dl']}T{raw['nof_antennas_ul']}R")
    if cell_bits:
        print(f"  Cell cfg      : {' '.join(cell_bits)}")
    print(f"  Duplex        : {'TDD' if cfg['tdd'] else 'FDD'}")
    if cfg["amf_addrs"]:
        port = cfg["amf_port"] or 38412
        print(f"  AMF           : {cfg['amf_addrs'][0]}:{port}"
              f" (bind={cfg['amf_bind_addrs'][0] if cfg['amf_bind_addrs'] else '?'})")
    if cfg["log_levels"]:
        levels = ", ".join(f"{k}={v}" for k, v in cfg["log_levels"].items())
        print(f"  Log levels    : {levels}")
    if cfg["pcaps"]:
        print(f"  PCAPs enabled : {', '.join(cfg['pcaps'])}")
    print()

    # ----- Run lifecycle -----
    print("=== Run Lifecycle ===")
    if log["first_ts"]:
        print(f"  First log ts        : {log['first_ts']}")
    if log["amf_connected_ts"]:
        print(f"  AMF SCTP connected  : {log['amf_connected_ts']}")
    if log["ng_setup"]:
        print(f"  NG setup            : {log['ng_setup']}")
    if log["last_ts"]:
        print(f"  Last log ts         : {log['last_ts']}")
    if log["first_ts"] and log["last_ts"]:
        d = ts_delta_seconds(log["first_ts"], log["last_ts"])
        if d is not None and d >= 0:
            print(f"  Duration            : {d:.1f} s")
    print(f"  Clean shutdown      : {'yes' if log['clean_shutdown'] else 'no — abnormal exit'}")
    if out["started"] and not out["stopped"]:
        print("  stdout marker       : started but no `Stopping...` line")
    print()

    # ----- Cells / UEs -----
    print("=== Cells & UEs ===")
    if log["cells_created"]:
        for ts, pci in log["cells_created"]:
            print(f"  {ts}  cell pci={pci} created")
    elif log["pcis_seen"]:
        print(f"  PCIs seen           : {', '.join(str(p) for p in log['pcis_seen'])}")
    if len(log["ue_creates"]) <= 10:
        for ts, ue, rnti in log["ue_creates"]:
            print(f"  {ts}  ue={ue} c-rnti=0x{rnti} created")
    else:
        print(f"  UE creations        : {len(log['ue_creates'])} (first @ {log['ue_creates'][0][0]},"
              f" last @ {log['ue_creates'][-1][0]})")
    if log["init_ctx_done"]:
        done = len(log["init_ctx_done"])
        attempted = len(log["ue_creates"]) or done
        print(f"  Initial Context Setup OK : {done}/{attempted}")
    if log["ue_releases"]:
        if len(log["ue_releases"]) <= 5:
            for ts, ue in log["ue_releases"]:
                print(f"  {ts}  ue={ue} released")
        else:
            print(f"  UE releases         : {len(log['ue_releases'])}")
    print()

    # ----- Procedures -----
    print("=== Procedures ===")
    print(f"  RRC reconfigs       : {log['rrc_reconfigs']}")
    print(f"  Handovers (Reconf w/Sync) : {log['ho_count']}")
    print(f"  NGAP handover msgs  : {log['ngap_handover_count']}")
    print(f"  Reestablishments    : {log['reest_count']}")
    print(f"  Bearer setups       : {log['bearer_setups']}")
    print(f"  Bearer modifications: {log['bearer_modifications']}")
    print(f"  Bearer releases     : {log['bearer_releases']}")
    print(f"  PRACH events        : {log['prach_events']}")
    print(f"  PHY CRC failures (crc=KO) : {log['crc_fails']}")
    # Caveat: these counters come from RRC/NGAP/F1AP/E1AP/CU layers. If those are
    # logged at 'warning', the layers are silent and the counts read 0 even when
    # the procedures happened — say so rather than implying nothing occurred.
    muted = [name for name, lvl in cfg["log_levels"].items()
             if lvl == "warning" and name in ("rrc", "ngap", "f1ap", "e1ap", "cu")]
    if muted:
        print(f"  NOTE: {', '.join(muted)} logged at 'warning' — the above procedure "
              f"counts are unreliable (layers silent). Infer HO from SCHED PRACH on the "
              f"target cell / metrics 'ue_reconf' events, or enable info logging.")
    print()

    # ----- Scheduler metrics rollup -----
    if met["records"]:
        print("=== Scheduler Metrics (from metrics.json) ===")
        print(f"  Records             : {met['records']}")
        print(f"  Peak DL bitrate/UE  : {met['peak_dl_brate']/1e6:.2f} Mbps")
        print(f"  Peak UL bitrate/UE  : {met['peak_ul_brate']/1e6:.2f} Mbps")
        print(f"  Max latency         : {met['max_latency_us']} us")
        print(f"  Late DL HARQs       : {met['late_dl_harqs']}")
        print(f"  Late UL HARQs       : {met['late_ul_harqs']}")
        print(f"  Failed PDCCH allocs : {met['failed_pdcch']}")
        print(f"  Failed UCI allocs   : {met['failed_uci']}")
        print(f"  Error indications   : {met['errors']}")
        print(f"  Msg3 ok/nok         : {met['msg3_ok']}/{met['msg3_nok']}"
              + ("  (high nok = RACH contention)" if met['msg3_nok'] else ""))
        if met["event_counts"]:
            evs = ", ".join(f"{n}×{k}" for k, n in met["event_counts"].most_common())
            print(f"  Events              : {evs}")
        print()
    elif log["metrics_rows"]:
        print("=== Scheduler Metrics (from [METRICS] log) ===")
        print(f"  Metrics rows in gnb.log : {log['metrics_rows']}")
        if log["last_metrics"]:
            print(f"  Last row:")
            print(f"    {log['last_metrics'][:200]}")
        print()

    # ----- Anomalies -----
    anomalies = []
    if not log["clean_shutdown"]:
        anomalies.append("No `Workers stopped successfully` line — abnormal exit")
    if log["ng_setup"] == "failure":
        anomalies.append("NGAP NG setup failed")
    elif log["ng_setup"] is None and log["amf_connected_ts"]:
        anomalies.append("NGSetupResponse not seen even though SCTP connected to AMF")
    if log["reest_count"] > 0:
        anomalies.append(f"RRC reestablishment requests: {log['reest_count']}")
    # UEs that got a context but never finished Initial Context Setup.
    if log["ue_creates"] and len(log["init_ctx_done"]) < len(log["ue_creates"]):
        anomalies.append(
            f"Initial Context Setup incomplete: {len(log['init_ctx_done'])}/"
            f"{len(log['ue_creates'])} UEs finished (rest may have been mid-attach "
            f"at capture end, or failed)"
        )
    if log["crc_fails"] > 100:
        anomalies.append(f"High PHY CRC failures (crc=KO): {log['crc_fails']}"
                         f" — may include Msg3 RACH contention in multi-UE runs")
    if met.get("msg3_nok", 0) > 0:
        total = met["msg3_ok"] + met["msg3_nok"]
        anomalies.append(f"Msg3 RACH failures: {met['msg3_nok']}/{total} "
                         f"(contention or coverage)")
    if log["errors"]:
        anomalies.append(f"Error-level log lines: {len(log['errors'])}"
                         f" (first: [{log['errors'][0][1]}] {log['errors'][0][2][:80]})")
    if log["warnings"]:
        anomalies.append(
            f"Warning-level log lines: {len(log['warnings'])}"
            f" (first: [{log['warnings'][0][1]}] {log['warnings'][0][2][:80]})"
        )
    if met["late_dl_harqs"] or met["late_ul_harqs"]:
        anomalies.append(f"Late HARQs: dl={met['late_dl_harqs']} ul={met['late_ul_harqs']}")
    if met["failed_pdcch"]:
        anomalies.append(f"Failed PDCCH allocs: {met['failed_pdcch']}")
    if met["errors"]:
        anomalies.append(f"MAC/scheduler error_indications: {met['errors']}")
    # UEs created but not released cleanly (and the run did stop)
    if log["ue_creates"] and log["clean_shutdown"]:
        n_create = len(log["ue_creates"])
        n_release = len(log["ue_releases"])
        if n_release < n_create:
            anomalies.append(
                f"UE releases ({n_release}) < UE creations ({n_create})"
            )

    print("=== Anomalies ===")
    if anomalies:
        for a in anomalies:
            print(f"  ! {a}")
    else:
        print("  None")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <gnb.log | run-dir | component-dir | test-dir>",
              file=sys.stderr)
        sys.exit(1)
    try:
        summarize(sys.argv[1])
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
