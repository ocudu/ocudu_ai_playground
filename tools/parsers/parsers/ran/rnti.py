# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""RNTIs (TS 38.321 7.1) in one form across artifacts: OCUDU logs print 0x4601, F1AP pcaps 17921, UE logs 4601."""

from __future__ import annotations


def normalize(rnti: str | int | None, bare_hex: bool = False) -> str | None:
    """RNTI as OCUDU logs print it, e.g. "0x4601", or None if empty or not a number.

    Strings are decimal unless prefixed with 0x, or hexadecimal with bare_hex, e.g. for UE logs.
    """
    if rnti is None or rnti == "":
        return None
    try:
        if isinstance(rnti, int):
            value = rnti
        else:
            text = rnti.strip().lower()
            value = int(text, 16) if text.startswith("0x") or bare_hex else int(text)
    except ValueError:
        return None
    return f"0x{value:04x}" if 0 <= value <= 0xFFFF else None
