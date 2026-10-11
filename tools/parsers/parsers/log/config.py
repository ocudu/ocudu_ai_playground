# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Parsing of the application configuration that OCUDU echoes at the top of its logs: log levels, node planes, cell
and AMF values, duplex mode and enabled pcaps.

The echo is logged by the CONFIG logger, with all values at debug level and only the non-default values at info level.
The same text format is used by the YAML configuration files, which parse_config() also accepts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from . import events

# Log levels, from least to most verbose.
LEVELS = ("none", "error", "warning", "info", "debug")
# Level of the layers that neither their own option nor all_level set.
DEFAULT_LEVEL = "warning"

# Logger name to the log level option that controls it, without the "_level" suffix.
LOGGER_OPTIONS = {
    "MAC": "mac",
    "SCHED": "mac",
    "PHY": "phy",
    "RLC": "rlc",
    "PDCP": "pdcp",
    "SDAP": "sdap",
    "RRC": "rrc",
    "NGAP": "ngap",
    "XNAP": "xnap",
    "CU-CP": "cu",
    "CU-UP": "cu",
    "CU-CP-F1": "f1ap",
    "DU-F1": "f1ap",
    "CU-CP-E1": "e1ap",
    "CU-UP-E1": "e1ap",
    "CU-F1-U": "f1u",
    "DU-F1-U": "f1u",
    "DU": "du",
    "DU-MNG": "du",
    "GTPU": "gtpu",
    "SEC": "sec",
    "FAPI": "fapi",
    "E2AP": "e2ap",
}

# Top-level configuration sections that reveal each plane of the node.
_PLANE_SECTIONS = {
    "CU-CP": re.compile(r"(?m)^cu_cp:"),
    "CU-UP": re.compile(r"(?m)^cu_up:"),
    "DU": re.compile(r"(?m)^(?:cells|cell_cfg|ru_sdr|ru_ofh|du_high):"),
}
# Scalar options kept in AppConfig.values.
VALUE_KEYS = (
    "gnb_id", "ran_node_name", "hex_max_size",
    "pci", "band", "dl_arfcn", "channel_bandwidth_MHz", "common_scs", "nof_antennas_dl", "nof_antennas_ul",
    "srate", "device_driver", "sync", "time_alignment_calibration",
    "enable_log", "enable_json", "autostart_stdout_metrics",
)
# Protocols of the "<proto>_enable: true" options of the pcap section.
PCAP_PROTOCOLS = ("ngap", "f1ap", "e1ap", "mac", "rlc", "n3", "f1u", "xnap", "e2ap_cu_cp", "e2ap_cu_up", "e2ap_du")
_VALUE_RES = {key: re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*(?:#.*)?$", re.MULTILINE) for key in VALUE_KEYS}
_PCAP_RE = re.compile(r"^\s*(\w+)_enable\s*:\s*true\s*$", re.MULTILINE)
_TDD_RE = re.compile(r"^\s*duplex\s*:\s*tdd\b", re.MULTILINE)
_ADDRS_RE = re.compile(r"^\s+addrs\s*:\s*(.+?)\s*$", re.MULTILINE)
_BIND_ADDRS_RE = re.compile(r"^\s+bind_addrs\s*:\s*(.+?)\s*$", re.MULTILINE)
_PORT_RE = re.compile(r"^\s+port\s*:\s*(\d+)\s*$", re.MULTILINE)
_IPV4_RE = re.compile(r"\d+\.\d+\.\d+\.\d+")
_ECHO_HEADER_RE = re.compile(r"input configuration \((?P<scope>all values|only non-default values)\)")
_LEVEL_RE = re.compile(r"^\s+(?P<option>\w+)_level\s*:\s*(?P<level>\w+)")
# Lines searched for the echo header before giving up.
_MAX_HEADER_LINES = 1000


@dataclass
class AppConfig:
    """Log levels, planes and main values of an OCUDU application, from its configuration."""

    # Explicitly configured log levels, by option name without the "_level" suffix.
    levels: dict[str, str] = field(default_factory=dict)
    # Planes of the node: "CU-CP", "CU-UP" and "DU".
    planes: list[str] = field(default_factory=list)
    # Whether the configuration has all values, rather than only the non-default ones.
    complete: bool = True
    # Values of the options of VALUE_KEYS that are set, as text, the last one where an option repeats.
    values: dict[str, str] = field(default_factory=dict)
    # Protocols of PCAP_PROTOCOLS with an enabled pcap, in the order first seen.
    pcaps: list[str] = field(default_factory=list)
    # Whether the cell is TDD.
    tdd: bool = False
    # IPv4 addresses of the AMF and of the local end of the connection to it, and the AMF port.
    amf_addrs: list[str] = field(default_factory=list)
    amf_bind_addrs: list[str] = field(default_factory=list)
    amf_port: int | None = None

    def level(self, option: str) -> str:
        """Effective log level of an option, e.g. "mac"."""
        if option in self.levels:
            return self.levels[option]
        if option != "config" and "all" in self.levels:
            return self.levels["all"]
        return "none" if option == "config" else DEFAULT_LEVEL

    def logger_level(self, logger: str) -> str | None:
        """Effective log level of a logger, e.g. "SCHED", or None if no option controls it."""
        option = LOGGER_OPTIONS.get(logger)
        return self.level(option) if option else None

    def logs_at(self, logger: str, level: str) -> bool:
        """Returns whether a logger prints messages of the given level."""
        effective = self.logger_level(logger)
        return effective is not None and LEVELS.index(effective) >= LEVELS.index(level)

    @property
    def node_type(self) -> str | None:
        """Node type, e.g. "gNB", "DU" or "CU", or None when no plane is configured."""
        planes = set(self.planes)
        if "DU" in planes and planes & {"CU-CP", "CU-UP"}:
            return "gNB"
        if planes == {"CU-CP", "CU-UP"}:
            return "CU"
        return "+".join(self.planes) or None


def parse_config(text: str, complete: bool = True) -> AppConfig:
    """Parses a configuration in the YAML format. Repeated keys keep the last value, as in concatenated documents."""
    cfg = AppConfig(complete=complete)
    in_log = False
    for line in text.splitlines():
        if line and not line[0].isspace():
            in_log = line.startswith("log:")
            continue
        if in_log and (m := _LEVEL_RE.match(line)):
            cfg.levels[m.group("option")] = m.group("level")
    cfg.planes = [plane for plane, pattern in _PLANE_SECTIONS.items() if pattern.search(text)]
    for key, pattern in _VALUE_RES.items():
        if values := pattern.findall(text):
            cfg.values[key] = values[-1].strip().strip('"')
    for proto in _PCAP_RE.findall(text):
        if proto in PCAP_PROTOCOLS and proto not in cfg.pcaps:
            cfg.pcaps.append(proto)
    cfg.tdd = "tdd_ul_dl_cfg" in text or _TDD_RE.search(text) is not None
    # The addresses of the AMF section, wherever it is nested, e.g. under cu_cp.
    cfg.amf_addrs = [v for v in (a.strip().strip('"') for a in _ADDRS_RE.findall(text)) if _IPV4_RE.match(v)]
    cfg.amf_bind_addrs = [v for v in (a.strip().strip('"') for a in _BIND_ADDRS_RE.findall(text)) if _IPV4_RE.match(v)]
    if m := _PORT_RE.search(text):
        cfg.amf_port = int(m.group(1))
    return cfg


def extract_echo(lines: Iterable[str]) -> tuple[str, bool] | None:
    """Returns the configuration echoed in a log and whether it has all values, or None if the log has no echo.

    Stops reading at the end of the echo, or after the first lines when there is none.
    """
    body: list[str] = []
    complete = None
    for line_no, line in enumerate(lines):
        if complete is None:
            if "[CONFIG" in line and (m := _ECHO_HEADER_RE.search(line)):
                complete = m.group("scope") == "all values"
            elif line_no >= _MAX_HEADER_LINES:
                return None
            continue
        if events.is_entry_start(line):
            break
        body.append(line)
    if complete is None:
        return None
    return "".join(body), complete


def from_log(lines: Iterable[str]) -> AppConfig | None:
    """Parses the configuration echoed in a log, or returns None if the log has no echo."""
    echo = extract_echo(lines)
    return parse_config(*echo) if echo else None
