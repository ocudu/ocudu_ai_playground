# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Grouping of the rows of a pcap into UEs."""

from __future__ import annotations

import os
from typing import Any

from ..ran.procedures import proc_name
from .tshark import Tshark
from .values import epoch_to_iso


def ue_ids_by_key(
    tshark: Tshark,
    pcap: str | os.PathLike[str],
    proto: str,
    key_field: str,
    other_field: str,
    names: tuple[str, str],
    tag: str,
    force: bool,
) -> list[dict[str, Any]]:
    """The UEs of a pcap identified by key_field, with the first other_field value seen, as names[0] and names[1].

    Each UE has its first frame and message, in order of appearance.
    """
    fields = ["frame.number", "frame.time_epoch", f"{proto}.procedureCode", key_field, other_field]
    clusters: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    key_name, other_name = names
    for frame, epoch, code, key, other in tshark.iter_fields(pcap, fields, tag=tag, force=force):
        # Rows without UE identifiers are procedures of the interface, e.g. NGSetup.
        if not epoch or not (key or other):
            continue
        epoch_f = float(epoch)
        frame_n = int(frame) if frame else None
        c = by_key.get(key) if key else None
        if c is None:
            c = {"frame": frame_n, "first_epoch": epoch_f, "first_code": code, key_name: None, other_name: None}
            clusters.append(c)
        if epoch_f < c["first_epoch"]:
            c.update(first_epoch=epoch_f, frame=frame_n, first_code=code)
        if key:
            if c[key_name] is None:
                c[key_name] = key
            by_key[key] = c
        if other and c[other_name] is None:
            c[other_name] = other
    clusters.sort(key=lambda c: c["first_epoch"])
    return [
        {
            "frame": c["frame"],
            "first_iso": epoch_to_iso(c["first_epoch"]),
            "message": proc_name(proto, c["first_code"], with_code=False),
            key_name: c[key_name],
            other_name: c[other_name],
            "first_epoch": c["first_epoch"],
        }
        for c in clusters
    ]
