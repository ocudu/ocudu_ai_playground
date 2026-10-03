# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Parsing of the METRICS logger lines into flat records with normalized units.

Times are normalized to "us", bitrates to "bps", and SI-prefixed unitless values
(e.g. 1.2k) to plain numbers. Unavailable values (n/a, NaN, ovl) become None.
Slot fields (sfn.slot) are kept as strings.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from . import preamble

if TYPE_CHECKING:
    import pandas

logger = logging.getLogger("parsers")

# Metric layer name to the pattern of its log context.
LAYER_PATTERNS = {
    "mac": re.compile(r"^MAC cell pci=(?P<pci>\d+) metrics:"),
    "rlc": re.compile(r"^RLC Metrics:"),
    "sched": re.compile(r"^Scheduler cell pci=(?P<pci>\d+) metrics:"),
    "sched_ue": re.compile(r"^Scheduler UE ue=(?P<ue>\d+) pci=(?P<pci>\d+) rnti=(?P<rnti>\S+) metrics:"),
    "exec": re.compile(r'^Executor metrics\s+"(?P<executor>[^"]+)"[^:]*:'),
    "upper_phy": re.compile(r"^Upper\ PHY.*sector#(?P<sector>\d+) metrics:"),
    "ofh": re.compile(r"^OFH metrics: timing metrics:"),
}

_SI_PREFIX = {
    "": Decimal(1),
    "p": Decimal("1e-12"),
    "n": Decimal("1e-9"),
    "u": Decimal("1e-6"),
    "m": Decimal("1e-3"),
    "k": Decimal("1e3"),
    "M": Decimal("1e6"),
    "G": Decimal("1e9"),
}
_SECONDS_TO_US = Decimal("1e6")
# Units printed apart from the value, mapped to their canonical name.
_SPACED_UNITS = {"MB": "MB", "Watts": "W", "segments": "segments"}

_key_re = re.compile(r"(?P<key>[A-Za-z_]\w*)= ?")
_section_re = re.compile(r"(?P<section>[A-Za-z_]\w*):(?=\s|$)")
_value_re = re.compile(
    r"(?P<hex>0x[0-9a-fA-F]+)\b"
    r"|(?P<na>n/a|\{na\}|NaN|ovl)"
    r"|(?P<num>[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?P<unit>[A-Za-z%]+)?"
    r"(?: (?P<spaced_unit>" + "|".join(_SPACED_UNITS) + r")\b)?"
    r"|(?P<word>[A-Za-z_][\w.-]*)"
)
_slot_value_re = re.compile(r"\d+\.\d+|n/a")
_slots_range_re = re.compile(r"^\s*(?P<start>\d+\.\d+),\s*(?P<end>\d+\.\d+)(?:\(\+(?P<hfn>\d+) HFNs\))?\s*$")
_remaining_re = re.compile(r"\((?P<count>\d+) remaining \w+\)")
_list_item_sep_re = re.compile(r"[,\s]+")


def parse_number(text: str) -> int | float | str:
    """Converts a numeric string to int or float, returning it unchanged on failure."""
    try:
        if any(c in text for c in ".eE"):
            return float(text)
        return int(text)
    except ValueError:
        return text


def parse_slot(slot: str) -> tuple[int, int]:
    """Splits a "sfn.slot" string into (sfn, slot_index)."""
    sfn, slot_index = slot.split(".")
    return int(sfn), int(slot_index)


def _is_slot_key(key: str) -> bool:
    return key == "slot" or key.endswith("_slot")


def _normalize(num: str, unit: str | None) -> tuple[int | float, str | None, bool]:
    """Scales a number to its canonical unit, returning (value, unit, unit_is_known)."""
    if unit is None:
        return parse_number(num), None, True
    if unit == "%":
        return parse_number(num), "%", True
    if unit == "usec":
        return parse_number(num), "us", True

    if unit.endswith("bps"):
        prefix, base, factor = unit[:-3], "bps", Decimal(1)
    elif unit.endswith("s"):
        prefix, base, factor = unit[:-1], "us", _SECONDS_TO_US
    else:
        prefix, base, factor = unit, None, Decimal(1)
    if prefix not in _SI_PREFIX:
        return parse_number(num), unit, False

    scaled = Decimal(num) * _SI_PREFIX[prefix] * factor
    printed_as_int = not any(c in num for c in ".eE")
    if printed_as_int and scaled == scaled.to_integral_value():
        return int(scaled), base, True
    return float(scaled), base, True


def _find_list_end(text: str, start: int) -> int:
    """Returns the index of the bracket closing the list or record opened at text[start]."""
    depth = 0
    paren_depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c in "[{":
            depth += 1
        elif c == "(":
            paren_depth += 1
        elif c in "]}" or (c == ")" and paren_depth == 0):
            # Slot ranges are printed half-open, as "[start, end)".
            depth -= 1
            if depth == 0:
                return i
        elif c == ")":
            paren_depth -= 1
    return len(text) - 1


class _FieldSink:
    """Accumulates the fields of one metrics text, with their units."""

    def __init__(self):
        self.fields: dict[str, Any] = {}
        self.units: dict[str, str] = {}
        self.unknown_units: dict[str, str] = {}

    def add(self, key: str, value: Any, unit: str | None = None, unit_is_known: bool = True):
        self.fields[key] = value
        if unit is None:
            return
        if unit_is_known:
            self.units[key] = unit
        else:
            self.unknown_units[key] = unit

    def merge(self, other: _FieldSink, prefix: str) -> None:
        """Adds the fields of other, with keys prefixed by "<prefix>_" if prefix is not empty."""

        def rename(k: str) -> str:
            return f"{prefix}_{k}" if prefix else k

        self.fields.update({rename(k): v for k, v in other.fields.items()})
        self.units.update({rename(k): u for k, u in other.units.items()})
        self.unknown_units.update({rename(k): u for k, u in other.unknown_units.items()})


def _parse_list(key: str, body: str, sink: _FieldSink) -> None:
    if key == "slots":
        m = _slots_range_re.match(body)
        if m:
            sink.add("slots_start", m.group("start"))
            sink.add("slots_end", m.group("end"))
            sink.add("slots_hfn_wraps", int(m.group("hfn") or 0))
            return

    if "{" in body:
        items = []
        pos = 0
        while (open_idx := body.find("{", pos)) >= 0:
            close_idx = _find_list_end(body, open_idx)
            items.append(extract_metric_fields(body[open_idx + 1:close_idx]))
            pos = close_idx + 1
        sink.add(key, items)
        remaining = _remaining_re.search(body, pos)
        if remaining:
            sink.add(f"{key}_remaining", int(remaining.group("count")))
        return

    if "=" in body:
        sub = _FieldSink()
        _parse_into(body, sub)
        sink.merge(sub, key.lower())
        return

    values = []
    for token in _list_item_sep_re.split(body.strip()):
        if not token:
            continue
        m = _value_re.fullmatch(token)
        if m and m.group("num") is not None:
            values.append(_normalize(m.group("num"), m.group("unit"))[0])
        else:
            values.append(None if m and m.group("na") else token)
    sink.add(key, values)


def _parse_value(key: str, text: str, pos: int, sink: _FieldSink) -> int:
    """Parses the value of key starting at text[pos], returning the position after it."""
    if pos < len(text) and text[pos] == "[":
        end = _find_list_end(text, pos)
        _parse_list(key, text[pos + 1:end], sink)
        return end + 1

    if _is_slot_key(key):
        m = _slot_value_re.match(text, pos)
        if m:
            sink.add(key, None if m.group() == "n/a" else m.group())
            return m.end()

    m = _value_re.match(text, pos)
    if not m:
        return pos
    if m.group("hex"):
        sink.add(key, m.group("hex"))
    elif m.group("na"):
        sink.add(key, None)
    elif m.group("num") is not None:
        if m.group("spaced_unit"):
            sink.add(key, parse_number(m.group("num")), _SPACED_UNITS[m.group("spaced_unit")])
        else:
            sink.add(key, *_normalize(m.group("num"), m.group("unit")))
    else:
        sink.add(key, m.group("word"))
    return m.end()


def _parse_into(text: str, sink: _FieldSink) -> None:
    """Scans key=value fields, prefixing the ones following a "<section>:" token.

    A section token only counts at the start of a ';' segment or right after a field, so that
    free-text labels like "PHY metrics:" do not become prefixes.
    """
    section = ""
    in_free_text = False
    pos = 0
    while pos < len(text):
        c = text[pos]
        if c == ";":
            section = ""
            in_free_text = False
            pos += 1
            continue
        if c.isspace() or c == ",":
            pos += 1
            continue

        m = _key_re.match(text, pos)
        if m:
            sub = _FieldSink()
            pos = _parse_value(m.group("key"), text, m.end(), sub)
            sink.merge(sub, section)
            in_free_text = False
            # Skips text that could not be parsed as a value.
            if pos == m.end():
                pos += 1
            continue

        m = _section_re.match(text, pos)
        if m:
            if not in_free_text:
                section = m.group("section")
            in_free_text = False
            pos = m.end()
            continue

        in_free_text = True
        while pos < len(text) and not text[pos].isspace() and text[pos] not in ";,":
            pos += 1


def extract_metric_fields(text: str) -> dict[str, Any]:
    """Extracts the key=value fields of a metrics text as a flat dict with normalized values."""
    sink = _FieldSink()
    _parse_into(text, sink)
    return sink.fields


class MetricsParser:
    """Parses METRICS log lines of the selected layers into flat records."""

    def __init__(self, layers: Sequence[str] | None = None):
        """Selects the metric layers to parse, or all known layers if None."""
        if layers is None:
            layers = list(LAYER_PATTERNS)
        unknown = [layer for layer in layers if layer not in LAYER_PATTERNS]
        if unknown:
            raise ValueError(f"Unknown metric layers {unknown}. Known layers: {list(LAYER_PATTERNS)}")
        self.layers = list(layers)
        # Canonical unit of each field, per layer, learned from the parsed lines.
        self.units: dict[str, dict[str, str]] = {layer: {} for layer in self.layers}
        # (layer, field) pairs already warned about.
        self._warned: set[tuple[str, str]] = set()

    def parse(self, line: str, preamble_match: re.Match | None = None) -> dict[str, Any] | None:
        """Parses a log line into a record, or returns None if it is not a metric of a selected layer."""
        if preamble_match is None:
            preamble_match = preamble.match_preamble(line)
        if not preamble_match or preamble_match.group("layer") != "METRICS":
            return None

        text = line[preamble_match.end():].rstrip("\n")
        for layer in self.layers:
            m = LAYER_PATTERNS[layer].match(text)
            if m:
                return self._make_record(layer, m, text[m.end():], preamble_match)
        return None

    def _make_record(self, layer: str, context_m: re.Match, text: str, preamble_match: re.Match) -> dict[str, Any]:
        record: dict[str, Any] = {
            "timestamp": datetime.fromisoformat(preamble_match.group("timestamp")),
            "layer": layer,
        }
        record.update({k: parse_number(v) for k, v in context_m.groupdict().items()})

        sink = _FieldSink()
        _parse_into(text, sink)
        record.update(sink.fields)

        layer_units = self.units[layer]
        for field, unit in sink.units.items():
            known = layer_units.setdefault(field, unit)
            if known != unit:
                self._warn_once(layer, field, f"Field {layer}.{field} has unit {unit!r}, expected {known!r}.")
        for field, unit in sink.unknown_units.items():
            self._warn_once(layer, field, f"Field {layer}.{field} has unknown unit {unit!r}. Value not normalized.")
        return record

    def _warn_once(self, layer: str, field: str, msg: str) -> None:
        if (layer, field) not in self._warned:
            self._warned.add((layer, field))
            logger.warning(msg)


def to_dataframe(lines: Iterable[str], layer: str) -> pandas.DataFrame:
    """Parses the metrics of one layer into a DataFrame, with the field units in df.attrs["units"].

    Requires the optional pandas dependency.
    """
    import pandas

    parser = MetricsParser([layer])
    records = (parser.parse(line) for line in lines)
    df = pandas.DataFrame.from_records([r for r in records if r is not None])
    df.attrs["units"] = dict(parser.units[layer])
    return df
