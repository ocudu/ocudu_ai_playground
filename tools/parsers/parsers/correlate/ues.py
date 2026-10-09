# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""UEs of a run: the UE contexts that its sources see, e.g. the F1AP UE contexts of a pcap and the UEs of a log,
combined into one UE context each, with the identifiers of all of them, see combine(), and the traces of the UEs
across contexts, e.g. through handovers, with their NGAP and E1AP contexts, see ue_traces().
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any, Hashable

from ..ran import rnti as rnti_util

# Slack around the lifetime of a UE in which a context of the same RNTI belongs to it, in seconds. The random access
# that a log prints before the first F1AP message of a UE is within it.
RNTI_SLACK_S = 2.0
# Largest gap between the creation of a context without RNTI and the start of its UE, in seconds, e.g. a log creating
# the target UE of a handover and the F1AP UEContextSetup of it.
CREATION_SLACK_S = 1.0


@dataclass
class Context:
    """UE context that one source sees, e.g. an F1AP UE context or a UE of a log."""

    source: Hashable
    # Id of the context in its source.
    lane: Hashable
    t_start: float
    t_end: float
    # Identifiers, e.g. {"rnti": "0x4601", "du_f1ap": "0"}, or {"du_ue": "0", "rnti": "0x4601"} for a log.
    ids: dict[str, str] = field(default_factory=dict)
    # Whether the context is still alive at the end of its source.
    open: bool = False
    # Values that link it to other contexts, with the time of their message, see ue_traces(): "ho_rnti", "reest_rnti",
    # "nas" and "teid".
    links: dict[str, Mapping[str, float]] = field(default_factory=dict)


@dataclass
class Ue:
    """UE context of a run, with the contexts of the sources that see it."""

    # "<source>:<lane>" of the context it was made from.
    key: str
    t_start: float
    t_end: float
    open: bool
    # Values of each identifier, in the order of its contexts.
    ids: dict[str, list[str]]
    # Contexts, as (source, lane).
    parts: list[tuple[Hashable, Hashable]]
    # Start of the context it was made from.
    created: float = 0.0
    # Link values of its contexts, with the time of their first message, see Context.
    links: dict[str, dict[str, float]] = field(default_factory=dict)

    def first(self, name: str) -> str | None:
        """First value of an identifier, or None."""
        values = self.ids.get(name)
        return values[0] if values else None


def combine(*sources: list[Context]) -> list[Ue]:
    """The UEs of a run from the contexts of its sources, the most reliable first, e.g. an F1AP pcap, then its logs.

    The contexts of the first source are UEs of their own. A context of a later source joins a UE made from an earlier
    one: with an RNTI, the UE of that RNTI whose lifetime, within RNTI_SLACK_S, overlaps it; without, the UE whose first
    context started nearest its creation, within CREATION_SLACK_S. Contexts of no UE are UEs of their own. UEs are in
    start order.
    """
    ues: list[Ue] = []
    for contexts in sources:
        index = _Index(ues)
        for ctx in contexts:
            ids = _normalized(ctx.ids)
            target = index.target(ctx, ids.get("rnti"))
            if target is None:
                ues.append(Ue(f"{ctx.source}:{ctx.lane}", ctx.t_start, ctx.t_end, ctx.open, {k: [v] for k, v in ids.items()},
                              [(ctx.source, ctx.lane)], ctx.t_start, {k: dict(v) for k, v in ctx.links.items()}))
                continue
            for name, values in ctx.links.items():
                known = target.links.setdefault(name, {})
                for value, t in values.items():
                    known[value] = min(t, known.get(value, t))
            target.parts.append((ctx.source, ctx.lane))
            target.t_start = min(target.t_start, ctx.t_start)
            target.t_end = max(target.t_end, ctx.t_end)
            target.open = target.open or ctx.open
            for name, value in ids.items():
                values = target.ids.setdefault(name, [])
                if value not in values:
                    values.append(value)
    return sorted(ues, key=lambda ue: (ue.t_start, ue.key))


@dataclass
class UeTrace:
    """UE followed through a run: its UE contexts, chained by handovers and reestablishments, and its NGAP and E1AP
    contexts.
    """

    # Number in the run, in start order.
    id: int
    t_start: float
    t_end: float
    # Keys of its UE contexts, see Ue, in start order.
    ues: list[str]
    # Identifiers of its UE contexts and of its NGAP and E1AP contexts, e.g. "ran_ngap", in start order.
    ids: dict[str, list[str]]
    # NGAP and E1AP contexts, as (source, lane).
    cores: list[tuple[Hashable, Hashable]]


def ue_traces(ues: list[Ue], cores: list[Context] = ()) -> list[UeTrace]:
    """The traces of the UE contexts of combine() and of the NGAP and E1AP contexts of a run, cores.

    A UE context joins the one that named its C-RNTI as the target of a handover (newUE-Identity), created within
    CREATION_SLACK_S of that message, and the one whose C-RNTI it reestablishes, and the ones of the same CU-CP UE index ("cu_ue")
    whose lifetimes overlap, since that index is soon reused. An NGAP context joins the UE contexts of the same NAS
    PDUs, the one created within CREATION_SLACK_S of the NGAP handover naming its C-RNTI, or else the one created nearest
    it within CREATION_SLACK_S, and an E1AP context the NGAP one of the same UPF TEID in a message within
    CREATION_SLACK_S. Each UE context gets "ue_trace", the trace number, and the identifiers of the NGAP and E1AP contexts of its
    trace.
    """
    parent = list(range(len(ues) + len(cores)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    by_rnti: dict[str, list[int]] = {}
    for i, ue in enumerate(ues):
        for rnti in ue.ids.get("rnti", ()):
            by_rnti.setdefault(rnti, []).append(i)

    def created_near(rnti: str, t: float, exclude: int = -1) -> int | None:
        # The UE context of an RNTI created nearest a message naming it, within CREATION_SLACK_S, since RNTIs are reused
        # by other cells and gNBs.
        near = [j for j in by_rnti.get(rnti, ()) if j != exclude and abs(ues[j].created - t) <= CREATION_SLACK_S]
        return min(near, key=lambda j: abs(ues[j].created - t), default=None)

    for i, ue in enumerate(ues):
        own = set(ue.ids.get("rnti", ()))
        for rnti, t in ue.links.get("ho_rnti", {}).items():
            if rnti not in own and (j := created_near(rnti, t, i)) is not None:
                union(i, j)
        for rnti, t in ue.links.get("reest_rnti", {}).items():
            olds = [j for j in by_rnti.get(rnti, ()) if j != i and ues[j].t_start <= t <= ues[j].t_end + RNTI_SLACK_S]
            if rnti not in own and olds:
                union(i, max(olds, key=lambda j: ues[j].t_start))
    by_cu_ue: dict[str, list[int]] = {}
    for i, ue in enumerate(ues):
        for cu_ue in ue.ids.get("cu_ue", ()):
            by_cu_ue.setdefault(cu_ue, []).append(i)
    for same in by_cu_ue.values():
        for a, b in zip(same, same[1:]):
            if ues[a].t_start <= ues[b].t_end and ues[b].t_start <= ues[a].t_end:
                union(a, b)

    by_nas: dict[str, int] = {}
    for i, ue in enumerate(ues):
        for nas in ue.links.get("nas", {}):
            by_nas.setdefault(nas, i)
    by_teid: dict[str, list[tuple[int, float]]] = {}
    ngap = [(len(ues) + k, c) for k, c in enumerate(cores) if "ran_ngap" in c.ids or "amf_ngap" in c.ids]
    unmatched = []
    with_ngap: set[int] = set()
    for node, core in ngap:
        matched = {by_nas[nas] for nas in core.links.get("nas", {}) if nas in by_nas}
        matched |= {j for rnti, t in core.links.get("ho_rnti", {}).items() if (j := created_near(rnti, t)) is not None}
        for i in matched:
            union(node, i)
        with_ngap |= matched
        if not matched:
            unmatched.append((node, core))
        for teid, t in core.links.get("teid", {}).items():
            by_teid.setdefault(teid, []).append((node, t))
    # NGAP contexts that no identifier links join the UE context created nearest them that has no NGAP context yet.
    for node, core in unmatched:
        near = [i for i, ue in enumerate(ues) if i not in with_ngap and abs(ue.created - core.t_start) <= CREATION_SLACK_S]
        if near:
            i = min(near, key=lambda i: abs(ues[i].created - core.t_start))
            union(node, i)
            with_ngap.add(i)
    for k, core in enumerate(cores):
        if "ran_ngap" in core.ids or "amf_ngap" in core.ids:
            continue
        # Some cores reuse UPF TEIDs, so the NGAP message must be near the E1AP one.
        near = [(abs(t - te), node) for teid, te in core.links.get("teid", {}).items() for node, t in by_teid.get(teid, ())
                if abs(t - te) <= CREATION_SLACK_S]
        if near:
            union(len(ues) + k, min(near)[1])

    groups: dict[int, list[int]] = {}
    for node in range(len(parent)):
        groups.setdefault(find(node), []).append(node)
    starts = [ue.t_start for ue in ues] + [c.t_start for c in cores]
    ends = [ue.t_end for ue in ues] + [c.t_end for c in cores]
    out: list[UeTrace] = []
    for nodes in sorted(groups.values(), key=lambda ns: min(starts[n] for n in ns)):
        nodes.sort(key=lambda n: starts[n])
        trace = UeTrace(len(out), min(starts[n] for n in nodes), max(ends[n] for n in nodes), [], {}, [])
        core_ids: dict[str, list[str]] = {}
        for n in nodes:
            if n < len(ues):
                trace.ues.append(ues[n].key)
                _merge(trace.ids, ues[n].ids)
            else:
                core = cores[n - len(ues)]
                trace.cores.append((core.source, core.lane))
                _merge(core_ids, {k: [v] for k, v in _normalized(core.ids).items()})
        _merge(trace.ids, core_ids)
        for n in nodes:
            if n < len(ues):
                ues[n].ids["ue_trace"] = [str(trace.id)]
                _merge(ues[n].ids, core_ids)
        out.append(trace)
    return out


def _merge(ids: dict[str, list[str]], more: dict[str, list[str]]) -> None:
    for name, values in more.items():
        known = ids.setdefault(name, [])
        known.extend(v for v in values if v not in known)


def _normalized(ids: dict[str, Any]) -> dict[str, str]:
    out = {name: str(value) for name, value in ids.items() if value is not None and value != ""}
    if "rnti" in out:
        rnti = rnti_util.normalize(ids["rnti"])
        if rnti is None:
            del out["rnti"]
        else:
            out["rnti"] = rnti
    return out


class _Index:
    """The UEs that the contexts of a source can join, by RNTI and by creation time."""

    def __init__(self, ues: list[Ue]):
        self._by_rnti: dict[str, list[Ue]] = {}
        for ue in ues:
            for rnti in ue.ids.get("rnti", ()):
                self._by_rnti.setdefault(rnti, []).append(ue)
        self._by_created = sorted(ues, key=lambda ue: ue.created)
        self._created = [ue.created for ue in self._by_created]

    def target(self, ctx: Context, rnti: str | None) -> Ue | None:
        """The UE a context joins, see combine(), or None."""
        if rnti is not None:
            candidates = [
                ue for ue in self._by_rnti.get(rnti, ())
                if ue.t_start - RNTI_SLACK_S <= ctx.t_end and ctx.t_start <= ue.t_end + RNTI_SLACK_S
            ]
            return min(candidates, key=lambda ue: abs(ue.t_start - ctx.t_start), default=None)
        lo = bisect.bisect_left(self._created, ctx.t_start - CREATION_SLACK_S)
        hi = bisect.bisect_right(self._created, ctx.t_start + CREATION_SLACK_S)
        return min(self._by_created[lo:hi], key=lambda ue: abs(ue.created - ctx.t_start), default=None)
