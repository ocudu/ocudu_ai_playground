# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Summary of the console output of an OCUDU application, e.g. the stdout.log of a test run: build banner, cells,
AMF connection, start and stop markers, and the rows of its metrics tables.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

_COMMIT_RE = re.compile(r"commit ([0-9a-fA-F]+)")
_LOGFILE_RE = re.compile(r"Logfile stored in (\S+)")
# A row of the console metrics table starts with the PCI and the RNTI, e.g. "   1 4601 |".
_METRICS_ROW_RE = re.compile(r"^\s*\d+\s+[0-9a-f]{4}\s+\|")


@dataclass
class ConsoleSummary:
    """Summary of the console output of an application."""

    # Commit of the build banner.
    banner_commit: str | None = None
    # The "Cell pci=..." lines.
    cells: list[str] = field(default_factory=list)
    amf_connected: bool = False
    started: bool = False
    stopped: bool = False
    logfile_path: str | None = None
    metrics_rows: int = 0


def summarize(lines: Iterable[str]) -> ConsoleSummary:
    """The summary of the lines of the console output of an application."""
    out = ConsoleSummary()
    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue
        # Banners of each application, e.g. "--== OCUDU gNB (commit ...) ==--" or "==== DU started ===".
        if stripped.startswith("--== OCUDU ") and "(commit" in stripped:
            if m := _COMMIT_RE.search(stripped):
                out.banner_commit = m.group(1)
        elif stripped.startswith("Cell pci="):
            out.cells.append(stripped)
        elif stripped.startswith("N2:") and "completed" in stripped:
            out.amf_connected = True
        elif stripped.startswith("==== ") and stripped.endswith(" started ==="):
            out.started = True
        elif stripped.startswith("Stopping..."):
            out.stopped = True
        elif stripped.startswith("Logfile stored in"):
            if m := _LOGFILE_RE.search(stripped):
                out.logfile_path = m.group(1)
        elif _METRICS_ROW_RE.match(line):
            out.metrics_rows += 1
    return out
