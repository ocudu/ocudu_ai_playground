# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Conversions of tshark field values."""

from __future__ import annotations

import datetime as _dt


def to_int(value: str | int | None, base: int = 0) -> int | None:
    """Integer of a tshark field value, e.g. "0x41" or "65", or None if empty or not a number."""
    try:
        return int(str(value), base)
    except (TypeError, ValueError):
        return None


def epoch_to_iso(epoch: float | str) -> str:
    """UTC ISO-8601 time of an epoch in seconds, with milliseconds and no zone suffix."""
    try:
        ts = float(epoch)
    except (TypeError, ValueError):
        return str(epoch)
    dt = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
