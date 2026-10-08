# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""UE contexts of an NGAP, F1AP or E1AP pcap: the messages of each UE, from its first message to the release of its
context, with its UE identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..ran.rnti import normalize as normalize_rnti
from .messages import UE_ID_FIELDS

# Procedure code that releases the UE context of each protocol, whose successful outcome ends the context.
RELEASE_CODES = {"ngap": "41", "f1ap": "6", "e1ap": "11"}
# Short names of the UE identifiers, by message field.
ID_NAMES = {
    "ran_ue_ngap_id": "ran_ngap",
    "amf_ue_ngap_id": "amf_ngap",
    "du_ue_f1ap_id": "du_f1ap",
    "cu_ue_f1ap_id": "cu_f1ap",
    "cu_cp_ue_e1ap_id": "cu_cp_e1ap",
    "cu_up_ue_e1ap_id": "cu_up_e1ap",
}


@dataclass
class UeContext:
    """UE context of a pcap."""

    id: int
    t_start: float
    t_end: float
    # UE identifiers by short name, e.g. {"du_f1ap": "0", "cu_f1ap": "0"}, the first value of each.
    ids: dict[str, str] = field(default_factory=dict)
    # C-RNTI, as logs print it, for F1AP.
    rnti: str | None = None
    released: bool = False

    def label(self) -> str:
        """Its identifiers, e.g. "du_f1ap=0 cu_f1ap=0"."""
        return " ".join(f"{name}={self.ids[name]}" for name in ID_NAMES.values() if name in self.ids)


class ContextTracker:
    """Assigns the messages of a pcap of proto, "ngap", "f1ap" or "e1ap", to UE contexts, given in file order.

    A message belongs to the context of any of its UE identifiers in use. Identifiers are free again once the context
    is released, since later UEs reuse them.
    """

    def __init__(self, proto: str):
        self.proto = proto
        self.contexts: list[UeContext] = []
        self._fields = [label for label, _ in UE_ID_FIELDS[proto]]
        self._in_use: dict[tuple[str, str], UeContext] = {}

    def assign(self, msg: dict[str, Any]) -> UeContext | None:
        """Returns the context of a message of messages.messages(), or None for messages of no UE."""
        ids = {f: msg[f] for f in self._fields if msg.get(f)}
        ctx = next((self._in_use[(k, v)] for k, v in ids.items() if (k, v) in self._in_use), None)
        if ctx is None and ids:
            ctx = UeContext(len(self.contexts), msg["epoch"], msg["epoch"])
            self.contexts.append(ctx)
        if ctx is None:
            return None
        ctx.t_end = max(ctx.t_end, msg["epoch"])
        for k, v in ids.items():
            self._in_use[(k, v)] = ctx
            ctx.ids.setdefault(ID_NAMES[k], v)
        if msg.get("crnti") and ctx.rnti is None:
            ctx.rnti = normalize_rnti(msg["crnti"])
        if msg["code"] == RELEASE_CODES[self.proto] and msg["outcome"] == "successful":
            ctx.released = True
            for k, v in ids.items():
                self._in_use.pop((k, v), None)
        return ctx


def ue_contexts(proto: str, msgs: list[dict[str, Any]]) -> list[UeContext]:
    """The UE contexts of the messages of a pcap of proto, see ContextTracker."""
    tracker = ContextTracker(proto)
    for msg in msgs:
        tracker.assign(msg)
    return tracker.contexts
