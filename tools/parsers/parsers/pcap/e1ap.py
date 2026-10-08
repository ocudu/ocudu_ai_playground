# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""E1AP pcaps: the UEs with their identifiers."""

from __future__ import annotations

import os
from typing import Any

from ._ues import ue_ids_by_key
from .tshark import Tshark


def ue_ids(tshark: Tshark, pcap: str | os.PathLike[str], *, force: bool = False) -> list[dict[str, Any]]:
    """The UEs of an E1AP pcap by gNB-CU-CP-UE-E1AP-ID, with the gNB-CU-UP-UE-E1AP-ID once assigned."""
    return ue_ids_by_key(
        tshark, pcap, "e1ap", "e1ap.GNB_CU_CP_UE_E1AP_ID", "e1ap.GNB_CU_UP_UE_E1AP_ID",
        ("e1_cp_ue_id", "e1_up_ue_id"), "e1ap-ue-ids-v1", force,
    )
