# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Trace of a run: the UE contexts of its F1AP pcap, joined with the UE events of its logs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from parsers.ran import rnti as rnti_util

from .filters import filter_rows
from .store import Store

# Slack around the lifetime of an F1AP UE context in which log events of its RNTI belong to it, in seconds. The random
# access logged before the first F1AP message of a UE is within it.
RNTI_SLACK_S = 2.0
# Largest gap between the creation of a UE in a log and the first F1AP message of its UE context, in seconds.
CREATION_SLACK_S = 1.0
# Lanes and events read from a store to join its lanes, without limit.
_ALL = 10**9
# Fields of the events that trace filters compare, with the UE index and RNTI of its lane for events without them.
FILTER_FIELDS = ("type", "category", "layer", "level", "ue", "rnti", "cause", "text")


def filter_trace(trace: dict[str, Any], expr: str, max_lanes: int, limit: int) -> dict[str, Any]:
    """A trace, as Store.trace() returns it with all its lanes and events, reduced to the events matching a filter
    expression over FILTER_FIELDS and the lanes they are in, then to max_lanes lanes and limit events.
    """
    lanes = {lane["lane"]: lane for lane in trace["lanes"]}
    rows = []
    for ev in trace["events"]:
        lane = lanes.get(ev["lane"], {})
        rows.append({**ev, "ue": ev["ue"] if ev["ue"] is not None else lane.get("ue"), "rnti": ev["rnti"] or lane.get("rnti")})
    kept = filter_rows(rows, expr, FILTER_FIELDS)
    in_lanes = {ev["lane"] for ev in kept}
    shown = [lane for lane in trace["lanes"] if lane["lane"] in in_lanes]
    shown_ids = {lane["lane"] for lane in shown[:max_lanes]}
    events = [ev for ev in kept if ev["lane"] is None or ev["lane"] in shown_ids]
    return {
        "lanes": shown[:max_lanes],
        "total_lanes": len(shown),
        "events": events[:limit],
        "total_events": len(events),
        "truncated": len(events) > limit,
    }


@dataclass
class _Lane:
    """UE context of the run trace: an F1AP UE context with the log lanes joined to it, or a log lane of none."""

    key: str
    t_start: float
    t_end: float
    label: str | None
    ue: int | None
    rnti: str | None
    open: bool
    # Lanes of the sources joined into this one, as (source id, lane id).
    parts: list[tuple[int, int]] = field(default_factory=list)


class RunTrace:
    """Joins the lanes of the logs of a run to the UE contexts of its F1AP pcap, see join_lanes()."""

    def __init__(self, anchor: tuple[int, Store], logs: list[tuple[int, Store]]):
        """anchor is the F1AP pcap of the run and logs its logs, each as (source id, store)."""
        self._sources = [anchor, *logs]
        self._lanes = join_lanes(anchor, logs)
        self._lane_of = {part: lane.key for lane in self._lanes for part in lane.parts}

    def trace(
        self,
        t0: float | None,
        t1: float | None,
        max_lanes: int,
        limit: int,
        sources: set[int] | None = None,
        filter_expr: str | None = None,
    ) -> dict[str, Any]:
        """Like Store.trace(), over the joined lanes, with the source of each event. Lane ids are strings.

        With sources, only their events and the lanes they have events in, e.g. the events of a log on the UE contexts
        of the F1AP pcap. With the F1AP pcap, the RRC events of the logs are left out, since its packets carry them.
        With filter_expr, see filter_trace().
        """
        if filter_expr:
            return filter_trace(self.trace(t0, t1, _ALL, _ALL, sources), filter_expr, max_lanes, limit)
        lo = -float("inf") if t0 is None else t0
        hi = float("inf") if t1 is None else t1
        active = [
            lane for lane in self._lanes
            if lane.t_start <= hi and (lane.t_end >= lo or lane.open)
            and (sources is None or any(source in sources for source, _ in lane.parts))
        ]
        shown = {lane.key for lane in active[:max_lanes]}
        events = []
        anchor = self._sources[0][0]
        # The packets of the F1AP pcap carry the RRC messages that its logs print, so they stand for them.
        drop_log_rrc = sources is None or anchor in sources
        for source, store in self._sources:
            if sources is not None and source not in sources:
                continue
            for ev in store.trace(t0, t1, _ALL, _ALL)["events"]:
                if drop_log_rrc and source != anchor and ev["category"] == "rrc":
                    continue
                key = self._lane_of.get((source, ev["lane"])) if ev["lane"] is not None else None
                if key is not None and key not in shown:
                    continue
                events.append({**ev, "lane": key, "source": source})
        events.sort(key=lambda e: e["t"])
        lanes = [
            {"lane": lane.key, "t_start": lane.t_start, "t_end": lane.t_end, "ue": lane.ue, "rnti": lane.rnti,
             "label": lane.label, "open": lane.open}
            for lane in active[:max_lanes]
        ]
        return {
            "lanes": lanes,
            "total_lanes": len(active),
            "events": events[:limit],
            "total_events": len(events),
            "truncated": len(events) > limit,
        }


def join_lanes(anchor: tuple[int, Store], logs: list[tuple[int, Store]]) -> list[_Lane]:
    """The UE contexts of the F1AP pcap, each with the log lanes of the same UE, then the log lanes of no context.

    A log lane with an RNTI joins the context with that C-RNTI whose lifetime, within RNTI_SLACK_S, overlaps it. A log
    lane without one, i.e. a UE created in the log without its RNTI, joins the context starting nearest its creation,
    within CREATION_SLACK_S. Lanes are in start order.
    """
    anchor_id, anchor_store = anchor
    lanes = [
        _Lane(f"{anchor_id}:{lane['lane']}", lane["t_start"], lane["t_end"], lane["label"], lane["ue"],
              rnti_util.normalize(lane["rnti"]), lane["open"], [(anchor_id, lane["lane"])])
        for lane in anchor_store.trace(None, None, _ALL, 0)["lanes"]
    ]
    unjoined = []
    for source, store in logs:
        for log_lane in store.trace(None, None, _ALL, 0)["lanes"]:
            target = _target(lanes, log_lane)
            part = (source, log_lane["lane"])
            if target is None:
                unjoined.append(
                    _Lane(f"{source}:{log_lane['lane']}", log_lane["t_start"], log_lane["t_end"], None, log_lane["ue"],
                          log_lane["rnti"], log_lane["open"], [part])
                )
                continue
            target.parts.append(part)
            target.t_start = min(target.t_start, log_lane["t_start"])
            target.t_end = max(target.t_end, log_lane["t_end"])
            if target.ue is None:
                target.ue = log_lane["ue"]
    return sorted(lanes + unjoined, key=lambda lane: (lane.t_start, lane.key))


def _target(lanes: list[_Lane], log_lane: dict[str, Any]) -> _Lane | None:
    rnti = rnti_util.normalize(log_lane["rnti"])
    start, end = log_lane["t_start"], log_lane["t_end"]
    if rnti is not None:
        candidates = [
            lane for lane in lanes
            if lane.rnti == rnti and lane.t_start - RNTI_SLACK_S <= end and start <= lane.t_end + RNTI_SLACK_S
        ]
    else:
        candidates = [lane for lane in lanes if abs(lane.t_start - start) <= CREATION_SLACK_S]
    return min(candidates, key=lambda lane: abs(lane.t_start - start), default=None)
