# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Shared setup of the analyze-ran-log pcap scripts.

The parsing lives in the parsers.pcap package of this repo, imported through scripts/_lib. TSHARK runs tshark with
its staged pcaps and cached extractions in the per-session cache directory, derived from CLAUDE_CODE_TMPDIR and
CLAUDE_CODE_SESSION_ID and shared by the other artifact types, and announces each cache file on stderr.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))

from parsers.pcap.tshark import Tshark, TsharkError  # noqa: E402,F401

CACHE_ROOT = (
    Path(os.environ.get("CLAUDE_CODE_TMPDIR", "/tmp"))
    / f"claude-skills-{os.environ.get('CLAUDE_CODE_SESSION_ID', 'default')}"
)


def _announce_cache(path: Path, hit: bool) -> None:
    # The docs tell the caller to quote this path instead of reconstructing the hash.
    print(f"cache: {path} ({'hit' if hit else 'miss'})", file=sys.stderr)


TSHARK = Tshark(CACHE_ROOT, on_cache=_announce_cache)

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("warning: %(message)s"))
logging.getLogger("parsers").addHandler(_handler)


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)
