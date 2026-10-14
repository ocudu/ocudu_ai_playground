# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Stages of the UE procedures that OCUDU logs as proc="..." traces, e.g. the DU-MNG, MAC, SCHED and DU-F1 steps of UE
creation, (re)configuration and removal, and the latencies between them.

Procedures are described by the labels of their stages, from the one that opens an instance to the one that closes it.
Stages that a build does not log are skipped, so that the latencies of the others are still measured.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from . import preamble

# Stages of each procedure, in order, as (key, exact label), or (key, labels) for a stage whose label changed between
# builds. The first opens an instance, the last closes it.
PROCEDURES: dict[str, list[tuple[str, str | tuple[str, ...]]]] = {
    "UE Create": [
        ("start", "Procedure started...."), ("resmgr", "Created DU UE resource manager."),
        ("ctxt", "Created DU UE context."), ("updres", "Updated UE ctxt resources."),
        ("srb", "Created DU UE SRB1."), ("f1ap", "Created DU UE F1AP."),
        ("rlc", "Created UE RLC bearers."), ("conn", "Connected UE bearers."),
        ("startmac", "Starting MAC UE creation."), ("maccreated", "MAC UE created."),
        ("flush", "Flushed CCCH."), ("done", "Procedure finished successfully."),
    ],
    "MAC UE Creation": [
        ("start", "started..."),
        ("ul", ("MAC UE UL context created successfully.", "UE UL context created successfully")),
        ("dl", ("MAC UE DL context created successfully.", "UE DL context created successfully")),
        ("ctx", "UE context created successfully"), ("done", "finished successfully"),
    ],
    "UE Configuration": [("start", "Procedure started...."), ("done", "Procedure finished successfully.")],
    "MAC UE Reconfiguration": [("start", "started..."), ("done", "finished successfully")],
    "Sched UE Config": [("start", "started..."), ("done", "successfully finished")],
    "UE Delete": [("start", "Procedure started...."), ("done", "Procedure finished successfully.")],
    "MAC UE Removal": [("start", "started..."), ("done", "finished successfully")],
    "UE Context Release": [
        ("start", "Started."), ("lower", "Initiate UE release in lower layers."), ("done", "Finished successfully."),
    ],
}

# Transitions measured instead of those between consecutive stages, as (label, from, to). A tuple of stages as from
# measures from the last of them.
TRANSITIONS: dict[str, list[tuple[str, str | tuple[str, ...], str]]] = {
    "MAC UE Creation": [
        ("start -> ul", "start", "ul"), ("start -> dl", "start", "dl"),
        ("ctx ready -> ctx created", ("ul", "dl"), "ctx"), ("ctx -> done", "ctx", "done"),
    ],
}

# Procedures by group, in report order.
GROUPS: list[tuple[str, list[str]]] = [
    ("CREATION", ["UE Create", "MAC UE Creation"]),
    ("CONFIGURATION", ["UE Configuration", "MAC UE Reconfiguration", "Sched UE Config"]),
    ("REMOVAL", ["UE Delete", "MAC UE Removal", "UE Context Release"]),
]

# UE, procedure and stage label of the message of a procedure line.
_PROC_RE = re.compile(r'(?<![\w-])(?:ue|du_ue)=(\d+).*?proc="([^"]+)": (.*?)\s*$')
_KEY_OF_LABEL = {
    proc: {label: key for key, labels in stages for label in ((labels,) if isinstance(labels, str) else labels)}
    for proc, stages in PROCEDURES.items()
}


@dataclass
class Instance:
    """One run of a procedure for a UE."""

    proc: str
    ue: int
    # Time of each stage logged, in microseconds since the epoch, by stage key.
    stages: dict[str, int] = field(default_factory=dict)


@dataclass
class Stats:
    """Statistics of latencies, in microseconds."""

    n: int
    mean: float
    p50: float
    p90: float
    p99: float
    max: float


def instances(lines: Iterable[str]) -> dict[str, list[Instance]]:
    """The instances of each procedure of PROCEDURES in a log, in the order they close.

    A stage logged without the opening one opens an instance. An instance that its opening stage reopens before it
    closed is kept as it is, and one left open at the end of the log is left out.
    """
    out: dict[str, list[Instance]] = {proc: [] for proc in PROCEDURES}
    open_: dict[tuple[int, str], Instance] = {}
    for line in lines:
        if 'proc="' not in line or not (h := preamble.match_header(line)) or not (m := _PROC_RE.search(line, h.end())):
            continue
        proc, label = m.group(2), m.group(3)
        key = _KEY_OF_LABEL.get(proc, {}).get(label)
        # Exact, so that latencies are.
        t = preamble.to_epoch_us(h.group("timestamp"))
        if key is None or t is None:
            continue
        ue = int(m.group(1))
        stages = PROCEDURES[proc]
        if key == stages[0][0] and (ue, proc) in open_:
            out[proc].append(open_.pop((ue, proc)))
        inst = open_.setdefault((ue, proc), Instance(proc, ue))
        inst.stages.setdefault(key, t)
        if key == stages[-1][0]:
            out[proc].append(open_.pop((ue, proc)))
    return out


def transitions(proc: str) -> list[tuple[str, str | tuple[str, ...], str]]:
    """The transitions measured for a procedure, as (label, from, to), the total from its first to its last stage last."""
    stages = PROCEDURES[proc]
    out = list(TRANSITIONS.get(proc) or [(f"{a} -> {b}", a, b) for (a, _), (b, _) in zip(stages, stages[1:])])
    first, last = stages[0][0], stages[-1][0]
    out.append((f"== TOTAL ({first}->{last})", first, last))
    return out


def latencies(insts: Iterable[Instance], frm: str | tuple[str, ...], to: str) -> list[int]:
    """The latencies, in microseconds, from a stage, or the last of several, to another, of the instances that logged
    them, without negative ones.
    """
    froms = frm if isinstance(frm, tuple) else (frm,)
    out = []
    for inst in insts:
        if to in inst.stages and all(k in inst.stages for k in froms):
            value = inst.stages[to] - max(inst.stages[k] for k in froms)
            if value >= 0:
                out.append(value)
    return out


def stats(values: list[float]) -> Stats | None:
    """The statistics of latencies, or None without any. Percentiles are nearest-rank."""
    if not values:
        return None
    ordered = sorted(values)

    def pct(p: float) -> float:
        return ordered[min(len(ordered) - 1, max(0, math.ceil(p / 100 * len(ordered)) - 1))]

    return Stats(len(ordered), sum(ordered) / len(ordered), pct(50), pct(90), pct(99), ordered[-1])

