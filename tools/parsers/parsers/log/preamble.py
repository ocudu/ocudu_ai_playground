# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Parsing of the OCUDU log line preamble: timestamp, logger, level and slot, and of its timestamp."""

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Iterator

# Start of the lines that begin a log entry, an ISO 8601 date. Other lines continue the previous entry, e.g. the
# "key: [value]" lines of the configuration echo. Usable as a bytes pattern too.
ENTRY_START_PATTERN = r"\d{4}-\d\d-\d\dT"

# Timestamp at the start of an entry line. Usable as a bytes pattern too.
TIMESTAMP_PATTERN = ENTRY_START_PATTERN + r"\S+"

_TIMESTAMP = rf"^(?P<timestamp>{TIMESTAMP_PATTERN})"
_LEVEL = r"\s*\]\s+(?:\[(?P<level>[A-Z])\]\s+)?"
_SLOT = r"\s*(?:\[\s*(?P<sfn>\d+)\.(?P<slot_index>\d+)\])?"

_header_pattern = re.compile(_TIMESTAMP + r"\s\[(?P<layer>.*?)" + _LEVEL)
_preamble_pattern = re.compile(_TIMESTAMP + r"\s\[(?P<layer>.*?)" + _LEVEL + _SLOT)
_EPOCH = datetime(1970, 1, 1)
_MICROSECOND = timedelta(microseconds=1)

# Cache of preamble patterns restricted to one logger name.
_layer_patterns: dict[str, re.Pattern] = {}


def _get_layer_pattern(layer: str) -> re.Pattern:
    if layer not in _layer_patterns:
        _layer_patterns[layer] = re.compile(
            _TIMESTAMP + rf"\s\[(?P<layer>{re.escape(layer)})" + _LEVEL + _SLOT
        )
    return _layer_patterns[layer]


def match_preamble(line: str, layer: str | None = None) -> re.Match | None:
    """Matches the log line preamble, optionally only for the given logger name."""
    if layer is not None:
        return _get_layer_pattern(layer).match(line)
    return _preamble_pattern.match(line)


def match_header(line: str) -> re.Match | None:
    """Matches the timestamp, logger and level of an entry line, ending where its message starts, slot included."""
    return _header_pattern.match(line)


def to_datetime(timestamp: str) -> datetime | None:
    """UTC time without a zone of a log timestamp, which OCUDU logs as UTC wall clock without a zone, or None if it
    is not one, e.g. two timestamps run together in a line cut short.
    """
    try:
        t = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    return t.astimezone(timezone.utc).replace(tzinfo=None) if t.tzinfo else t


def to_epoch(timestamp: str) -> float | None:
    """Seconds since the epoch of a log timestamp, see to_datetime(), or None."""
    t = to_datetime(timestamp)
    return None if t is None else t.replace(tzinfo=timezone.utc).timestamp()


def to_epoch_us(timestamp: str) -> int | None:
    """Exact microseconds since the epoch of a log timestamp, see to_datetime(), or None."""
    t = to_datetime(timestamp)
    return None if t is None else (t - _EPOCH) // _MICROSECOND


def tokenize_multiline_logs(stream: Iterable[str]) -> Iterator[tuple[re.Match | None, list[str]]]:
    """Groups lines into log entries, yielding the preamble match and the entry lines.

    Lines before the first preamble are yielded one by one with a None match.
    """
    token_lines: list[str] = []
    last_match = None
    for line in stream:
        m = match_preamble(line)
        if m:
            if last_match is not None:
                yield last_match, token_lines
            token_lines = [line]
            last_match = m
        elif last_match is None:
            yield None, [line]
        else:
            token_lines.append(line)
    if last_match is not None:
        yield last_match, token_lines
