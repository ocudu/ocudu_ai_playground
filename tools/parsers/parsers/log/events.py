# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Recognition of events in OCUDU logs, such as random access, UE creation, RRC messages, handovers and radio link
failures.

Events are recognized by their message, since most failures are logged at info level. Warning and error lines that no
pattern recognizes are reported as generic "warning" or "error" events, in the category of the same name.

Some messages change format with the log level of their logger. At debug level, the scheduler prints its slot events
one per continuation line below the entry header, while at info level it prints them inline. Patterns are therefore
bound to the level of the entry, and a log entry may hold several events.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from . import preamble

# Event categories, in display order.
CATEGORIES = ("ra", "lifecycle", "rrc", "mobility", "failure", "warning", "error")


@dataclass(frozen=True)
class EventPattern:
    """A kind of event: its type, category, logger and the message pattern that recognizes it.

    With item, the entry holds one event per match of item, searched in the message or, with in_body, in each
    continuation line. With level, the pattern only applies to entries of that level.
    """

    type: str
    category: str
    layer: str
    pattern: re.Pattern
    item: re.Pattern | None = None
    level: str | None = None
    in_body: bool = False


def _p(type_: str, category: str, layer: str, pattern: str, item: str | None = None, **kwargs) -> EventPattern:
    return EventPattern(type_, category, layer, re.compile(pattern), re.compile(item) if item else None, **kwargs)


_PRACH_INFO = r"prach\((?:ra|msgb)-rnti=0x\w+ preamble=(?P<preamble>\d+)(?: ssb=\d+)? tc-rnti=(?P<rnti>0x\w+)\)"
_PRACH_DEBUG = r"^- PRACH: slot=\S+ preamble=(?P<preamble>\d+) (?:ra|msgb)-rnti=0x\w+ temp_crnti=(?P<rnti>0x\w+)"

EVENT_PATTERNS = (
    _p("prach", "ra", "SCHED", r"^Processed slot events pci=\d+: ", _PRACH_INFO, level="I"),
    _p("prach", "ra", "SCHED", r"^Processed slot events pci=\d+:$", _PRACH_DEBUG, level="D", in_body=True),
    _p("msg3", "ra", "MAC", r"UL rnti=(?P<rnti>0x\w+) subPDUs: \[CCCH"),
    _p("conres", "ra", "MAC", r"DL PDU: ue=(?P<ue>\d+) rnti=(?P<rnti>0x\w+) size=\d+: CON_RES"),
    _p("ue_create", "lifecycle", "DU-MNG", r'ue=(?P<ue>\d+)(?: rnti=(?P<rnti>0x\w+))? proc="UE Create": Procedure started'),
    _p("ue_delete", "lifecycle", "DU-MNG", r'ue=(?P<ue>\d+) proc="UE Delete": Procedure finished successfully'),
    _p("rrc_setup_complete", "rrc", "RRC", r"ue=(?P<ue>\d+) c-rnti=(?P<rnti>0x\w+): DCCH UL rrcSetupComplete$"),
    _p("rrc_release", "rrc", "RRC", r"ue=(?P<ue>\d+) c-rnti=(?P<rnti>0x\w+): DCCH DL rrcRelease$"),
    _p("rrc_reest_request", "rrc", "RRC", r"ue=(?P<ue>\d+) c-rnti=(?P<rnti>0x\w+): CCCH UL rrcReestablishmentRequest$"),
    _p("ho_trigger", "mobility", "CU-CP", r"ue=(?P<ue>\d+): Trigger intra-CU \((?:inter|intra)-DU\) handover"),
    _p("ho_preparation", "mobility", "NGAP", r"ue=(?P<ue>\d+) ran_ue=\d+ amf_ue=\d+: Starting HO preparation"),
    _p("rlf", "failure", "MAC", r"ue=(?P<ue>\d+): RLF detected\. Cause: (?P<cause>.*)"),
    _p("rlf", "failure", "DU-MNG", r'ue=(?P<ue>\d+) rnti=(?P<rnti>0x\w+): RLF detected with cause "(?P<cause>[^"]+)"'),
    _p("rrc_reest_failed", "failure", "RRC", r'ue=(?P<ue>\d+) c-rnti=(?P<rnti>0x\w+): "RRC Reestablishment Procedure".* failed\. Cause: (?P<cause>.*)'),
    _p("rrc_reest_rejected", "failure", "RRC", r"ue=(?P<ue>\d+) c-rnti=(?P<rnti>0x\w+): Rejecting RRC Reestablishment.*Cause: (?P<cause>.*?)\.(?: |$)"),
)

# Substrings of the entry headers that can hold events, to skip the other lines without parsing them. Usable as a
# bytes pattern too, to skip lines before decoding them.
CANDIDATE_PATTERN = (
    r'Processed slot events|subPDUs: \[CCCH|CON_RES|proc="UE (?:Create|Delete)"|rrcSetupComplete|rrcRelease'
    r"|rrcReestablishmentRequest|Trigger intra-CU|Starting HO preparation|RLF detected|Reestablishment|\] \[[WE]\] "
)
# Start of the lines that begin a log entry. Other lines continue the previous entry. Usable as a bytes pattern too.
ENTRY_START_PATTERN = r"\d{4}-\d\d-\d\dT"

_CANDIDATE_RE = re.compile(CANDIDATE_PATTERN)
_ENTRY_START_RE = re.compile(ENTRY_START_PATTERN)
_LEVEL_EVENTS = {"W": "warning", "E": "error"}
_BODY_KEYS = {(p.layer, p.level) for p in EVENT_PATTERNS if p.in_body}


def is_candidate(line: str) -> bool:
    """Returns whether an entry header may hold events. Cheap check to skip most lines before parse()."""
    return _CANDIDATE_RE.search(line) is not None


def is_entry_start(line: str) -> bool:
    """Returns whether a line begins a log entry, rather than continuing the previous one."""
    return _ENTRY_START_RE.match(line) is not None


def has_body(preamble_match: re.Match) -> bool:
    """Returns whether the events of an entry may be in its continuation lines, which parse() then needs."""
    return (preamble_match.group("layer").strip(), preamble_match.group("level")) in _BODY_KEYS


def parse(line: str, body: Sequence[str] = (), preamble_match: re.Match | None = None) -> list[dict[str, Any]]:
    """Parses a log entry, given by its header line and continuation lines, into its event records.

    Each record has the timestamp, type, category, layer, level, ue and rnti (None when not logged), cause (or None)
    and the message text.
    """
    if preamble_match is None:
        preamble_match = preamble.match_preamble(line)
    if not preamble_match:
        return []
    layer = preamble_match.group("layer").strip()
    level = preamble_match.group("level")
    text = line[preamble_match.end():].strip()

    found: list[tuple[str, str, dict[str, Any], str]] = []
    for ev in EVENT_PATTERNS:
        if ev.layer != layer or (ev.level is not None and ev.level != level):
            continue
        m = ev.pattern.search(text)
        if not m:
            continue
        if ev.item is None:
            found.append((ev.type, ev.category, m.groupdict(), text))
        elif ev.in_body:
            for body_line in map(str.strip, body):
                if im := ev.item.search(body_line):
                    found.append((ev.type, ev.category, {**m.groupdict(), **im.groupdict()}, body_line.removeprefix("- ")))
        else:
            for im in ev.item.finditer(text):
                found.append((ev.type, ev.category, {**m.groupdict(), **im.groupdict()}, im.group(0)))
        break
    if not found and (level_type := _LEVEL_EVENTS.get(level or "")):
        found.append((level_type, level_type, {}, text))

    timestamp = datetime.fromisoformat(preamble_match.group("timestamp"))
    return [
        {
            "timestamp": timestamp,
            "type": type_,
            "category": category,
            "layer": layer,
            "level": level,
            "ue": int(groups["ue"]) if groups.get("ue") is not None else None,
            "rnti": groups.get("rnti"),
            "cause": groups.get("cause"),
            "text": ev_text,
        }
        for type_, category, groups, ev_text in found
    ]


def iter_events(lines: Iterable[str]) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yields the events of a log, with the line number of the entry header they come from, starting at 1."""
    pending: tuple[int, str, re.Match, list[str]] | None = None
    for line_no, line in enumerate(lines, start=1):
        if pending is not None:
            if not is_entry_start(line):
                pending[3].append(line)
                continue
            for ev in parse(pending[1], pending[3], pending[2]):
                yield pending[0], ev
            pending = None
        if not is_candidate(line) or not (m := preamble.match_preamble(line)):
            continue
        if has_body(m):
            pending = (line_no, line, m, [])
        else:
            for ev in parse(line, preamble_match=m):
                yield line_no, ev
    if pending is not None:
        for ev in parse(pending[1], pending[3], pending[2]):
            yield pending[0], ev
