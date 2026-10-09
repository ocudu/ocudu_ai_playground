# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""UE contexts of an NGAP, F1AP or E1AP pcap: the messages of each UE, from its first message to the release of its
context, with its UE identifiers.
"""

from __future__ import annotations

import hashlib
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
# Messages whose GTP TEIDs are the UL ones of the UPF, which NGAP and E1AP share, by protocol: NGAP
# HandoverResourceAllocation, InitialContextSetup and PDUSessionResourceSetup requests, E1AP BearerContextSetup requests. The TEIDs that the gNB allocates repeat across
# UEs.
_UPF_TEID_CODES = {"ngap": {"13", "14", "29"}, "e1ap": {"8"}}
# InitialULRRCMessageTransfer, whose RRC reestablishment request holds the old C-RNTI of the UE.
_INITIAL_UL_RRC_CODE = "11"


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
    # Values that link it to other contexts, with the time of their first message, see ContextTracker: "ho_rnti"
    # (target C-RNTIs of its handovers), "reest_rnti" (C-RNTI of the context it reestablishes), "nas" (hashes of its
    # NAS PDUs) and "teid" (UPF TEIDs).
    links: dict[str, dict[str, float]] = field(default_factory=dict)

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
        for label, values in (msg.get("links") or {}).items():
            for value in self._link_values(label, values, msg):
                ctx.links.setdefault(label, {}).setdefault(value, msg["epoch"])
        if msg["code"] == RELEASE_CODES[self.proto] and msg["outcome"] == "successful":
            ctx.released = True
            for k, v in ids.items():
                self._in_use.pop((k, v), None)
        return ctx


    def _link_values(self, label: str, values: list[str], msg: dict[str, Any]) -> list[str]:
        if label in ("ho_rnti", "reest_rnti"):
            if label == "reest_rnti" and msg["code"] != _INITIAL_UL_RRC_CODE:
                return []
            return [r for v in values if (r := normalize_rnti(v))]
        if label == "nas":
            return [hashlib.sha1(v.lower().encode()).hexdigest()[:16] for v in values]
        if label == "teid":
            if msg["outcome"] != "initiating" or msg["code"] not in _UPF_TEID_CODES.get(self.proto, ()):
                return []
            return [v.lower() for v in values]
        return values


def ue_contexts(proto: str, msgs: list[dict[str, Any]]) -> list[UeContext]:
    """The UE contexts of the messages of a pcap of proto, see ContextTracker."""
    tracker = ContextTracker(proto)
    for msg in msgs:
        tracker.assign(msg)
    return tracker.contexts
