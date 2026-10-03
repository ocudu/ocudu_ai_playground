# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Parsing of the METRICS logger lines into named fields."""

import re
from datetime import datetime

from . import preamble

# Field names are word chars and underscores. Values are numbers with an optional unit, or [ ] lists.
_field_pattern = re.compile(
    r"(?P<key>[A-Za-z_]\w*)=("
    r"\[(?P<list>.+?)(?:\](?=[\s;,]|$)|\)(?=[\s;,]|$))"
    r"|(?P<value>[+-]?\d+(?:\.\d+)?)(?P<unit>[A-Za-z%]+)?)"
)
_number_pattern = re.compile(r"[+-]?\d+(?:\.\d+)?")
_section_pattern = re.compile(r"\s*(?P<section>[A-Za-z_]+):")

# Metric layer name to the pattern of its log context.
LAYER_PATTERNS = {
    "mac": re.compile(r"^MAC cell pci=(?P<pci>\d+) metrics:"),
    "rlc": re.compile(r"^RLC Metrics:"),
    "sched": re.compile(r"^Scheduler cell pci=(?P<pci>\d+) metrics:"),
    "sched_ue": re.compile(r"^Scheduler UE ue=(?P<ue_id>\d+) pci=(?P<pci>\d+) rnti=(?P<rnti>[^\s]+) metrics:"),
    "exec": re.compile(r'^Executor metrics\s+"(?P<execname>[^"]+)"[^:]*:'),
    "upper_phy": re.compile(r"^Upper\ PHY.*sector#(?P<sector>\d+) metrics:"),
    "ofh": re.compile(r"^OFH metrics: timing metrics:"),
}

_MULT_FACTOR = {"kbps": 1000, "Mbps": 1e6, "Gbps": 1e9, "k": 1000, "M": 1e6}


def parse_int_or_float(number: str) -> int | float | str:
    """Converts a numeric string to int or float, returning it unchanged on failure."""
    try:
        if "." in number:
            return float(number)
        return int(number)
    except ValueError:
        return number


def regularize_units(fields: dict[str, tuple]) -> None:
    """Converts bitrates to bps and k/M multipliers to plain values, in place."""
    for k, v in fields.items():
        if v[1] in ("kbps", "Mbps", "Gbps"):
            fields[k] = (v[0] * _MULT_FACTOR[v[1]], "bps")
        elif v[1] in ("k", "M"):
            fields[k] = (v[0] * _MULT_FACTOR[v[1]], "")


def _expand_list(m: re.Match) -> dict[str, tuple]:
    key = m.group("key")
    subfields = {
        f"{key}_{m2.group('key')}": (parse_int_or_float(m2.group("value")), m2.group("unit") or "")
        for m2 in _field_pattern.finditer(m.group("list"))
    }
    if subfields:
        return subfields
    return {key: ([parse_int_or_float(n) for n in _number_pattern.findall(m.group("list"))], "")}


def extract_metric_fields(text: str) -> dict[str, tuple]:
    """Extracts all key=value fields of a metrics text as {name: (value, unit)}.

    Lists of key=value pairs are flattened as <key>_<subkey>, and ';' sections
    starting with <section>: get their fields prefixed with <section>_.
    """
    fields: dict[str, tuple] = {}
    for subtext in text.split(";"):
        section_fields: dict[str, tuple] = {}
        for m in _field_pattern.finditer(subtext):
            if m.group("value"):
                section_fields[m.group("key")] = (parse_int_or_float(m.group("value")), m.group("unit") or "")
            else:
                section_fields.update(_expand_list(m))

        section_m = _section_pattern.match(subtext)
        if section_m:
            prefix = section_m.group("section")
            section_fields = {f"{prefix}_{k}": v for k, v in section_fields.items()}

        fields.update(section_fields)

    regularize_units(fields)
    return fields


def parse_fields(logline: str, metric_layer: str, preamble_match: re.Match | None = None) -> dict[str, tuple] | None:
    """Parses a METRICS log line of the given layer into {name: (value, unit)}.

    Returns None if the line does not belong to the given metric layer.
    """
    if not preamble_match:
        preamble_match = preamble.match_preamble(logline)
    if not preamble_match or preamble_match.group("layer") != "METRICS":
        return None

    text = logline[preamble_match.end():]
    m = LAYER_PATTERNS[metric_layer].match(text)
    if not m:
        return None

    fields = {k: (parse_int_or_float(v), "") for k, v in m.groupdict().items()}
    fields.update(extract_metric_fields(text[m.end():]))
    fields["timestamp"] = (datetime.fromisoformat(preamble_match.group("timestamp")), "")
    return fields
