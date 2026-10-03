# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Parsing of the OCUDU log line preamble: timestamp, logger, level and slot."""

import re
from typing import Iterable, Iterator

_PREAMBLE_TAIL = (
    r"\s*\]\s+(?:\[(?P<level>[A-Z])\]\s+)?\s*"
    r"(?:\[\s*(?P<sfn>\d+)\.(?P<slot_index>\d+)\])?"
)

_preamble_pattern = re.compile(r"^(?P<timestamp>\S+)\s\[(?P<layer>.*?)" + _PREAMBLE_TAIL)

# Cache of preamble patterns restricted to one logger name.
_layer_patterns: dict[str, re.Pattern] = {}


def _get_layer_pattern(layer: str) -> re.Pattern:
    if layer not in _layer_patterns:
        _layer_patterns[layer] = re.compile(
            rf"^(?P<timestamp>\S+)\s\[(?P<layer>{re.escape(layer)})" + _PREAMBLE_TAIL
        )
    return _layer_patterns[layer]


def match_preamble(line: str, layer: str | None = None) -> re.Match | None:
    """Matches the log line preamble, optionally only for the given logger name."""
    if layer is not None:
        return _get_layer_pattern(layer).match(line)
    return _preamble_pattern.match(line)


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
