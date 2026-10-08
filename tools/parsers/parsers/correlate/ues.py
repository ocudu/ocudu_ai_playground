# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""UEs of a run: the UE contexts that its sources see, e.g. the F1AP UE contexts of a pcap and the UEs of a log,
combined into one UE each, with the identifiers of all of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    # Identifiers, e.g. {"rnti": "0x4601", "du_f1ap": "0"}, or {"ue": "0", "rnti": "0x4601"} for a log.
    ids: dict[str, str] = field(default_factory=dict)
    # Whether the context is still alive at the end of its source.
    open: bool = False


@dataclass
class Ue:
    """UE of a run, with the contexts of the sources that see it."""

    # "<source>:<lane>" of the context it was made from.
    key: str
    t_start: float
    t_end: float
    open: bool
    # Values of each identifier, in the order of its contexts.
    ids: dict[str, list[str]]
    # Contexts, as (source, lane).
    parts: list[tuple[Hashable, Hashable]]

    def first(self, name: str) -> str | None:
        """First value of an identifier, or None."""
        values = self.ids.get(name)
        return values[0] if values else None


def combine(*sources: list[Context]) -> list[Ue]:
    """The UEs of a run from the contexts of its sources, the most reliable first, e.g. an F1AP pcap, then its logs.

    The contexts of the first source are UEs of their own. A context of a later source joins a UE made from an earlier
    one: with an RNTI, the UE of that RNTI whose lifetime, within RNTI_SLACK_S, overlaps it; without, the UE starting
    nearest its creation, within CREATION_SLACK_S. Contexts of no UE are UEs of their own. UEs are in start order.
    """
    ues: list[Ue] = []
    for contexts in sources:
        earlier = list(ues)
        for ctx in contexts:
            ids = _normalized(ctx.ids)
            target = _target(earlier, ctx, ids.get("rnti"))
            if target is None:
                ues.append(Ue(f"{ctx.source}:{ctx.lane}", ctx.t_start, ctx.t_end, ctx.open, {k: [v] for k, v in ids.items()},
                              [(ctx.source, ctx.lane)]))
                continue
            target.parts.append((ctx.source, ctx.lane))
            target.t_start = min(target.t_start, ctx.t_start)
            target.t_end = max(target.t_end, ctx.t_end)
            target.open = target.open or ctx.open
            for name, value in ids.items():
                values = target.ids.setdefault(name, [])
                if value not in values:
                    values.append(value)
    return sorted(ues, key=lambda ue: (ue.t_start, ue.key))


def _normalized(ids: dict[str, Any]) -> dict[str, str]:
    out = {name: str(value) for name, value in ids.items() if value is not None and value != ""}
    if "rnti" in out:
        rnti = rnti_util.normalize(ids["rnti"])
        if rnti is None:
            del out["rnti"]
        else:
            out["rnti"] = rnti
    return out


def _target(ues: list[Ue], ctx: Context, rnti: str | None) -> Ue | None:
    if rnti is not None:
        candidates = [
            ue for ue in ues
            if rnti in ue.ids.get("rnti", ()) and ue.t_start - RNTI_SLACK_S <= ctx.t_end and ctx.t_start <= ue.t_end + RNTI_SLACK_S
        ]
    else:
        candidates = [ue for ue in ues if abs(ue.t_start - ctx.t_start) <= CREATION_SLACK_S]
    return min(candidates, key=lambda ue: abs(ue.t_start - ctx.t_start), default=None)
