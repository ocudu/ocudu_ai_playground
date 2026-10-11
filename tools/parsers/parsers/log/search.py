# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Search of the entries of OCUDU logs by logger, level, UE, RNTI, PCI, time and pattern.

An entry is a timestamped line and the continuation lines below it, e.g. an ASN.1 body or a SIB1 dump, and filters
match anywhere in it. The configuration echo at the top of a log is left out unless asked for.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

# Entry lines start with an ISO 8601 timestamp, unlike continuation lines and the body of the configuration echo.
_HEADER_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T(?P<time>\d{2}:\d{2}:\d{2}\.\d{6}))\s+"
    r"\[(?P<layer>[A-Z][A-Z0-9_ -]*?)\s*\]\s+"
    # The level is absent on some loggers, e.g. METRICS.
    r"(?:\[(?P<lvl>[A-Z])\]\s+)?"
)


@dataclass
class Filter:
    """Conditions that an entry must all meet. Unset ones match any entry."""

    # Logger, e.g. RRC, matched exactly but for case.
    layer: str | None = None
    # Regex that the level letter, e.g. "E|W", must match whole.
    level: str | None = None
    # UE index, matched as a "ue=N" token.
    ue: str | None = None
    # RNTI in hex without 0x, matched as "rnti=0x", "c-rnti=0x" or "tc-rnti=0x" tokens.
    rnti: str | None = None
    # PCI, matched as a "pci=N" token.
    pci: str | None = None
    # Bounds of the time of the entry, inclusive: ISO timestamps, or times of day such as HH:MM:SS.mmm compared to the
    # same precision.
    after: str | None = None
    before: str | None = None
    # Regex searched in the entry, ignoring case, with ^ and $ at its lines.
    pattern: str | None = None

    def __post_init__(self) -> None:
        self._level = re.compile(self.level) if self.level else None
        self._ue = re.compile(rf"\bue={re.escape(self.ue)}\b") if self.ue is not None else None
        self._rnti = (re.compile(rf"(?:c-|tc-)?rnti=0x{re.escape(self.rnti)}\b", re.IGNORECASE)
                      if self.rnti is not None else None)
        self._pci = re.compile(rf"\bpci={re.escape(self.pci)}\b") if self.pci is not None else None
        self._pattern = re.compile(self.pattern, re.IGNORECASE | re.MULTILINE) if self.pattern else None

    def matches(self, entry: list[str]) -> bool:
        """Whether an entry of entries() meets the conditions."""
        m = _HEADER_RE.match(entry[0])
        if not m:
            return False
        if self.after and not _at_or_after(m.group("ts"), m.group("time"), self.after):
            return False
        if self.before and not _at_or_before(m.group("ts"), m.group("time"), self.before):
            return False
        if self.layer and m.group("layer").strip().upper() != self.layer.upper():
            return False
        if self._level and not self._level.fullmatch(m.group("lvl") or ""):
            return False
        text = "\n".join(entry)
        return all(p is None or p.search(text) for p in (self._ue, self._rnti, self._pci, self._pattern))


def entries(lines: Iterable[str], include_config_echo: bool = False) -> Iterator[list[str]]:
    """The entries of a log, each as its lines without line ends, empty lines left out, and lines before the first
    entry too.
    """
    entry: list[str] | None = None
    skipping = False
    for raw in lines:
        line = raw.rstrip("\n")
        if not line:
            continue
        if m := _HEADER_RE.match(line):
            if entry is not None:
                yield entry
            skipping = not include_config_echo and _is_config_echo(m, line)
            entry = None if skipping else [line]
        elif entry is not None and not skipping:
            entry.append(line)
    if entry is not None:
        yield entry


def search(lines: Iterable[str], flt: Filter, include_config_echo: bool = False) -> Iterator[str]:
    """The text of the entries of a log that meet a filter."""
    for entry in entries(lines, include_config_echo):
        if flt.matches(entry):
            yield "\n".join(entry)


def _is_config_echo(m: re.Match, line: str) -> bool:
    """Whether an entry line is the header of the configuration echo, whose body is the effective configuration."""
    return m.group("layer").strip() == "CONFIG" and m.group("lvl") == "D" and "gnb input configuration" in line.lower()


def _at_or_after(ts: str, time: str, ref: str) -> bool:
    return ts >= ref if "T" in ref else time[: len(ref)] >= ref


def _at_or_before(ts: str, time: str, ref: str) -> bool:
    return ts <= ref if "T" in ref else time[: len(ref)] <= ref
