# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Parsing of the METRICS logger lines into flat records with normalized units.

Times are normalized to "us", bitrates to "bps", and SI-prefixed unitless values
(e.g. 1.2k) to plain numbers. Fields printed without a unit get the one in IMPLIED_UNITS. Unavailable values (n/a, NaN, ovl) become None.
Slot fields (sfn.slot) are kept as strings.

Lines of a layer mostly share a layout, so after parsing a line the parser learns a pattern of its layout, and parses
later lines with that layout in one match. Lines that match no learned pattern use the full parser.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from . import preamble

if TYPE_CHECKING:
    import pandas

logger = logging.getLogger("parsers")

# Metric layer name to the pattern of its log context.
LAYER_PATTERNS = {
    "du_manager": re.compile(r"^DU manager metrics:"),
    "mac": re.compile(r"^MAC cell pci=(?P<pci>\d+) metrics:"),
    "sched": re.compile(r"^Scheduler cell pci=(?P<pci>\d+) metrics:"),
    "sched_ue": re.compile(r"^Scheduler UE ue=(?P<ue>\d+) pci=(?P<pci>\d+) rnti=(?P<rnti>\S+) metrics:"),
    "rlc": re.compile(r"^RLC Metrics:"),
    "phy": re.compile(r"^PHY metrics:"),
    "ofh_timing": re.compile(r"^OFH timing metrics:"),
    "ofh_sector": re.compile(r"^OFH sector#(?P<sector>\d+) metrics: pci=(?P<pci>\d+) received messages stats:"),
    "pdcp": re.compile(r"^PDCP Metrics:"),
    "nrup": re.compile(r"^NRUP Metrics:"),
    "e1ap": re.compile(r"^CU-UP E1AP metrics:"),
    "exec": re.compile(r'^Executor metrics\s+"(?P<executor>[^"]+)"[^:]*:'),
    "resource_usage": re.compile(r"^App resource usage:"),
    "buffer_pool": re.compile(r"^Buffer pool:"),
}

# Units of fields printed without one, per layer. "s" values are normalized to "us".
IMPLIED_UNITS = {
    "sched": {"avg_prach_delay": "slots"},
    "sched_ue": {
        "dl_bs": "bytes",
        "bsr": "bytes",
        "dl_olla": "dB",
        "ul_olla": "dB",
        "last_phr": "dB",
        "pusch_snr_db": "dB",
        "pusch_rsrp_db": "dBFS",
    },
    "rlc": {"tx_pull_latency_avg": "s"},
    "e1ap": {"release_latency_avg": "s"},
    "ofh_sector": {
        "earliest_msg_us": "us",
        "latest_msg_us": "us",
        "ether_rx_rx_bytes": "bytes",
        "ether_tx_tx_bytes": "bytes",
    },
}

# Powers of ten of the SI prefixes.
_SI_PREFIX = {"": 0, "p": -12, "n": -9, "u": -6, "\u00b5": -6, "m": -3, "k": 3, "M": 6, "G": 9}
# Power of ten from seconds to the canonical "us".
_SECONDS_TO_US = 6
# Units printed apart from the value, mapped to their canonical name.
_SPACED_UNITS = {"MB": "MB", "Watts": "W", "segments": "segments"}

_VALUE = (
    r"(?P<hex>0x[0-9a-fA-F]+)\b"
    r"|(?P<na>n/a|\{na\}|NaN|ovl)"
    r"|(?P<num>[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?P<unit>[A-Za-z%\u00b5]+)?"
    r"(?: (?P<spaced_unit>" + "|".join(_SPACED_UNITS) + r")\b)?"
    r"|(?P<word>[A-Za-z_][\w.-]*)"
)
_value_re = re.compile(_VALUE)
# One token of a metrics text: a ';', a key=value field, a "<section>:" token, or free text.
_token_re = re.compile(
    r"[\s,]*(?:"
    r"(?P<semi>;)"
    r"|(?P<key>[A-Za-z_]\w*)= ?(?:(?P<list>\[)|" + _VALUE + r")?"
    r"|(?P<section>[A-Za-z_]\w*):(?=\s|$)"
    r"|[^\s;,]+"
    r")"
)
_slots_range_re = re.compile(r"^\s*(?P<start>\d+\.\d+),\s*(?P<end>\d+\.\d+)(?:\(\+(?P<hfn>\d+) HFNs\))?\s*$")
_optional_re = re.compile(r"optional\((?P<value>[^()]*)\)")
_remaining_re = re.compile(r"\((?P<count>\d+) remaining \w+\)")
_list_item_sep_re = re.compile(r"[,\s]+")


def parse_number(text: str) -> int | float | str:
    """Converts a numeric string to int or float, returning it unchanged on failure."""
    try:
        if "." in text or "e" in text or "E" in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def parse_slot(slot: str) -> tuple[int, int]:
    """Splits a "sfn.slot" string into (sfn, slot_index)."""
    sfn, slot_index = slot.split(".")
    return int(sfn), int(slot_index)


def _is_slot_key(key: str) -> bool:
    return key == "slot" or (key.endswith("_slot") and not key.endswith("_per_slot"))


@lru_cache(maxsize=None)
def _unit_scale(unit: str) -> tuple[str | None, int | None]:
    """Canonical unit of a unit and the power of ten that scales values to it, or None for unknown prefixes."""
    if unit in ("%", "usec"):
        return ("us" if unit == "usec" else unit), 0
    if unit.endswith("bps"):
        prefix, base, exponent = unit[:-3], "bps", 0
    elif unit.endswith("s"):
        prefix, base, exponent = unit[:-1], "us", _SECONDS_TO_US
    else:
        prefix, base, exponent = unit, None, 0
    if prefix not in _SI_PREFIX:
        return unit, None
    return base, exponent + _SI_PREFIX[prefix]


def _scale(num: str, exponent: int) -> int | float:
    """Scales a number by a power of ten, as an int when it was printed as one and stays integral.

    Integer and float operations are exact or correctly rounded, so results match decimal arithmetic.
    """
    if "." in num or "e" in num or "E" in num:
        if exponent == 0:
            return float(num)
        mantissa, _, power = num.lower().partition("e")
        return float(f"{mantissa}e{int(power or 0) + exponent}")
    value = int(num)
    if exponent >= 0:
        return value * 10**exponent
    divisor = 10**-exponent
    return value // divisor if value % divisor == 0 else value / divisor


def _normalize(num: str, unit: str | None) -> tuple[int | float, str | None, bool]:
    """Scales a number to its canonical unit, returning (value, unit, unit_is_known)."""
    if unit is None:
        return parse_number(num), None, True
    base, exponent = _unit_scale(unit)
    if exponent is None:
        return parse_number(num), base, False
    return _scale(num, exponent), base, True


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

    def __init__(self, implied_units: dict[str, str] | None = None):
        self.fields: dict[str, Any] = {}
        self.units: dict[str, str] = {}
        self.unknown_units: dict[str, str] = {}
        # Units of fields printed without one.
        self.implied_units = implied_units or {}

    def add(self, name: str, value: Any, unit: str | None = None, unit_is_known: bool = True):
        self.fields[name] = value
        if unit is None:
            return
        if unit_is_known:
            self.units[name] = unit
        else:
            self.unknown_units[name] = unit


def _parse_list(key: str, base: str, body: str, sink: _FieldSink) -> None:
    """Parses the body of the list field base+key."""
    name = base + key
    if key == "slots":
        m = _slots_range_re.match(body)
        if m:
            sink.add(f"{name}_start", m.group("start"))
            sink.add(f"{name}_end", m.group("end"))
            sink.add(f"{name}_hfn_wraps", int(m.group("hfn") or 0))
            return

    if body.lstrip().startswith("{"):
        items = []
        pos = 0
        while (open_idx := body.find("{", pos)) >= 0:
            close_idx = _find_list_end(body, open_idx)
            items.append(extract_metric_fields(body[open_idx + 1:close_idx]))
            pos = close_idx + 1
        sink.add(name, items)
        remaining = _remaining_re.search(body, pos)
        if remaining:
            sink.add(f"{name}_remaining", int(remaining.group("count")))
        return

    if "=" in body:
        _parse_into(body, sink, f"{base}{key.lower()}_")
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
    sink.add(name, values)


def _add_number(sink: _FieldSink, name: str, num: str, unit: str | None) -> None:
    implied = sink.implied_units.get(name)
    if implied is None or (unit is not None and unit not in _SI_PREFIX):
        sink.add(name, *_normalize(num, unit))
    elif implied == "s":
        sink.add(name, *_normalize(num, (unit or "") + "s"))
    else:
        sink.add(name, _normalize(num, unit)[0], implied)


def _add_value(sink: _FieldSink, name: str, key: str, m: re.Match) -> None:
    """Adds the scalar value matched by the _VALUE groups of m, if any."""
    _add_scalar(sink, name, _is_slot_key(key), *m.group("hex", "na", "num", "unit", "spaced_unit", "word"))


def _add_scalar(
    sink: _FieldSink,
    name: str,
    is_slot: bool,
    hex_: str | None,
    na: str | None,
    num: str | None,
    unit: str | None,
    spaced_unit: str | None,
    word: str | None,
) -> None:
    """Adds a scalar value, given by the text of the _VALUE groups that matched it."""
    if num is not None:
        if is_slot:
            sink.add(name, num)
        elif spaced_unit:
            sink.add(name, parse_number(num), _SPACED_UNITS[spaced_unit])
        else:
            _add_number(sink, name, num, unit)
    elif na:
        sink.add(name, None)
    elif hex_:
        sink.add(name, hex_)
    elif word:
        sink.add(name, word)


# Value patterns of templates, as atomic groups that keep the first alternative that matches, like the tokenizer.
# Any value: the _VALUE groups without names, i.e. hex, na, num, unit, spaced unit and word.
_ANY_VALUE = "(?>" + re.sub(r"\(\?P<\w+>", "(", _VALUE) + ")"
# A number with an optional unit, or n/a: num, unit and na. Excludes what _VALUE matches as hex, which comes first.
_NUMBER_VALUE = r"(?>(?!0x[0-9a-fA-F]+\b)([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)([A-Za-z%\u00b5]+)?(?![ ](?:" + "|".join(_SPACED_UNITS) + r")\b)|(n/a|\{na\}|NaN|ovl))"
# Templates kept per layer, since free text that varies between lines would otherwise create one per line.
_MAX_TEMPLATES = 32


class _Template:
    """Layout of the metrics texts of one line shape: a pattern capturing each value, and the field of each value.

    Fields whose value was a number with an optional unit, or n/a, match only those and are converted inline. The other
    fields match any value and go through _add_scalar().
    """

    def __init__(self, pattern: re.Pattern, fields: list[tuple[str, bool, bool, str | None, int]]):
        self.pattern = pattern
        # Name of each field, whether it is a plain number field, whether it is a slot, its implied unit and the index
        # of its first group.
        self.fields = fields

    @staticmethod
    def build(text: str, implied_units: dict[str, str]) -> _Template | None:
        """Template of a metrics text, or None for texts with lists or valueless fields, which need the full parser.

        Follows _parse_into() token by token, so that a text matching the template parses into the same fields.
        """
        parts: list[str] = []
        fields: list[tuple[str, bool, bool, str | None, int]] = []
        nof_groups = 0
        base = ""
        in_free_text = False
        pos = 0
        while (m := _token_re.match(text, pos)) is not None and m.end() > pos:
            key = m.group("key")
            if key:
                in_free_text = False
                if m.group("list"):
                    return None
                value_start = min((m.start(g) for g in ("hex", "na", "num", "word") if m.start(g) >= 0), default=-1)
                if value_start < 0:
                    return None
                parts.append(re.escape(text[pos:value_start]))
                plain = (m.group("num") is not None and not m.group("spaced_unit")) or m.group("na") is not None
                parts.append(_NUMBER_VALUE if plain else _ANY_VALUE)
                name = base + key
                fields.append((name, plain, _is_slot_key(key), implied_units.get(name), nof_groups))
                nof_groups += 3 if plain else 6
            else:
                parts.append(re.escape(text[pos:m.end()]))
                if m.group("section"):
                    if not in_free_text:
                        base = f"{m.group('section')}_"
                    in_free_text = False
                elif m.group("semi"):
                    base = ""
                    in_free_text = False
                else:
                    in_free_text = True
            pos = m.end()
        parts.append(re.escape(text[pos:]))
        return _Template(re.compile("".join(parts)), fields)

    def parse(self, text: str, sink: _FieldSink) -> bool:
        """Adds the fields of a text to sink if the text has this layout, returning whether it had."""
        m = self.pattern.fullmatch(text)
        if m is None:
            return False
        groups = m.groups()
        fields = sink.fields
        units = sink.units
        # Same outcomes as _add_scalar() and _add_number(), inlined for the common plain number fields.
        for name, plain, is_slot, implied, i in self.fields:
            if not plain:
                _add_scalar(sink, name, is_slot, *groups[i:i + 6])
                continue
            num = groups[i]
            if num is None:
                fields[name] = None
                continue
            if is_slot:
                fields[name] = num
                continue
            unit = groups[i + 1]
            if implied is not None and implied != "s" and (unit is None or unit in _SI_PREFIX):
                fields[name] = parse_number(num) if unit is None else _scale(num, _SI_PREFIX[unit])
                units[name] = implied
            elif implied is not None:
                _add_number(sink, name, num, unit)
            elif unit is None:
                fields[name] = parse_number(num)
            else:
                base, exponent = _unit_scale(unit)
                if exponent is None:
                    fields[name] = parse_number(num)
                    sink.unknown_units[name] = unit
                else:
                    fields[name] = _scale(num, exponent)
                    units[name] = base
        return True


def _parse_into(text: str, sink: _FieldSink, prefix: str = "") -> None:
    """Scans key=value fields, prefixing the ones following a "<section>:" token.

    A section token only counts at the start of a ';' segment or right after a field, so that
    free-text labels like "PHY metrics:" do not become prefixes.
    """
    base = prefix
    in_free_text = False
    pos = 0
    while (m := _token_re.match(text, pos)) is not None and m.end() > pos:
        pos = m.end()
        key = m.group("key")
        if key:
            in_free_text = False
            if m.group("list"):
                end = _find_list_end(text, pos - 1)
                _parse_list(key, base, text[pos:end], sink)
                pos = end + 1
            else:
                _add_value(sink, base + key, key, m)
        elif m.group("section"):
            if not in_free_text:
                base = f"{prefix}{m.group('section')}_"
            in_free_text = False
        elif m.group("semi"):
            base = prefix
            in_free_text = False
        else:
            in_free_text = True


def _parse_text(text: str, sink: _FieldSink) -> None:
    # Some optional values are printed through fmt's std::optional formatter.
    if "optional(" in text:
        text = _optional_re.sub(r"\g<value>", text)
    _parse_into(text, sink)


def extract_metric_fields(text: str) -> dict[str, Any]:
    """Extracts the key=value fields of a metrics text as a flat dict with normalized values."""
    sink = _FieldSink()
    _parse_text(text, sink)
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
        # Layouts of the metrics texts seen per layer, most recently matched first.
        self._templates: dict[str, list[_Template]] = {layer: [] for layer in self.layers}

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

        sink = _FieldSink(IMPLIED_UNITS.get(layer))
        self._parse_fields(layer, text, sink)
        record.update(sink.fields)

        layer_units = self.units[layer]
        for field, unit in sink.units.items():
            known = layer_units.setdefault(field, unit)
            if known != unit:
                self._warn_once(layer, field, f"Field {layer}.{field} has unit {unit!r}, expected {known!r}.")
        for field, unit in sink.unknown_units.items():
            self._warn_once(layer, field, f"Field {layer}.{field} has unknown unit {unit!r}. Value not normalized.")
        return record

    def _parse_fields(self, layer: str, text: str, sink: _FieldSink) -> None:
        """Parses the fields of a metrics text, through the template of its layout when one was learned."""
        templates = self._templates[layer]
        if "optional(" not in text:
            for i, template in enumerate(templates):
                if template.parse(text, sink):
                    # Lines of a layer mostly share one layout, so the last match is tried first.
                    if i:
                        templates.insert(0, templates.pop(i))
                    return
            if len(templates) < _MAX_TEMPLATES and (template := _Template.build(text, sink.implied_units)) is not None:
                templates.insert(0, template)
        _parse_text(text, sink)

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
