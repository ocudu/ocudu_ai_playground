# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Resource grid occupancy of a schedtrace: the allocations of each slot as rectangles of symbols and CRBs, and their
occupancy of groups of CRBs.

Allocations are placed as the trace allows: VRBs map to PRBs one to one (non-interleaved), PRBs of a BWP to CRBs from
the BWP start, and RBGs have the size of TS 38.214 Table 5.1.2.2.1-1 configuration 1 for the size of the BWP. The VRBs
of PDSCHs of DCI format 1_0 in a common search space (SIB, RAR, paging, fallback) count from the lowest CRB of the
CORESET of their PDCCH, TS 38.214 5.1.2.2.2, those of the other PDSCHs from the BWP start. PDCCH, PRACH and SRS are
left out. The UL allocations of a slot decision are those transmitted in its slot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NOF_SYMBOLS = 14
# Channels of the allocations, DL then UL.
DL_CHANNELS = ("PDSCH", "SIB", "RAR", "Paging", "SSB", "CSI-RS")
UL_CHANNELS = ("PUSCH", "PUCCH")
CHANNELS = DL_CHANNELS + UL_CHANNELS
# Slot duration of each subcarrier spacing, in seconds.
SLOT_DURATION_S = {"Khz15": 1e-3, "Khz30": 0.5e-3, "Khz60": 0.25e-3, "Khz120": 0.125e-3, "Khz240": 0.0625e-3}
# DlPdcch.dci_type values, as dci_dl_rnti_config_type of OCUDU; all but C_RNTI_F1_1 are DCI format 1_0.
SI_F1_0, RA_F1_0, C_RNTI_F1_0, TC_RNTI_F1_0, P_RNTI_F1_0, C_RNTI_F1_1 = range(6)


@dataclass
class Cell:
    """What placing the allocations of a cell needs, from its start event. BWPs have "cp", "scs", "crb_start" and
    "crb_length".
    """

    dl_bwp: dict[str, Any]
    ul_bwp: dict[str, Any]
    pucch_resources: list[dict[str, Any]] = field(default_factory=list)
    # Coreset and SearchSpace tables of the DL BWP.
    coresets: list[dict[str, Any]] = field(default_factory=list)
    search_spaces: list[dict[str, Any]] = field(default_factory=list)

    @property
    def nof_crbs(self) -> int:
        """CRBs up to the end of the widest BWP."""
        return max(b["crb_start"] + b["crb_length"] for b in (self.dl_bwp, self.ul_bwp))

    @property
    def slot_duration_s(self) -> float:
        return SLOT_DURATION_S.get(self.dl_bwp["scs"], 1e-3)


def cell_of(start_event: dict[str, Any]) -> Cell:
    """The cell of a CellStartEvent of schedtrace.read()."""
    dl, ul = start_event["init_dl_bwp"], start_event["init_ul_bwp"]
    return Cell(_bwp(dl["generic_params"]), _bwp(ul["generic_params"]), ul.get("pucch_resources") or [],
                dl.get("coresets") or [], dl.get("search_spaces") or [])


def _bwp(params: dict[str, Any]) -> dict[str, Any]:
    crbs = params["crbs"]
    return {"cp": params["cp"], "scs": params["scs"], "crb_start": crbs["start"], "crb_length": crbs["length"]}


def rbg_size(nof_prbs: int) -> int:
    """Nominal RBG size of a BWP of nof_prbs PRBs, TS 38.214 Table 5.1.2.2.1-1, configuration 1."""
    return 2 if nof_prbs <= 36 else 4 if nof_prbs <= 72 else 8 if nof_prbs <= 144 else 16


def allocations(slot_event: dict[str, Any], cell: Cell) -> list[dict[str, Any]]:
    """The allocations of a CellSlotEvent of schedtrace.read() as rectangles: "dir" ("DL" or "UL"), "channel",
    "sym_start", "sym_length", "crb_start", "crb_length", "item", the list of the decision and the index in it of the
    allocation, e.g. ["ue_pdschs", 3], and "rnti" and the details of the grant when it has them. A frequency-hopping
    allocation gives one rectangle per hop.
    """
    decision = slot_event.get("decision") or {}
    out: list[dict[str, Any]] = []

    def add(direction: str, channel: str, sym_start: int, sym_length: int, crbs: list[tuple[int, int]], info: dict[str, Any]) -> None:
        for crb_start, crb_length in crbs:
            if crb_length > 0 and sym_length > 0:
                out.append({"dir": direction, "channel": channel, "sym_start": sym_start, "sym_length": sym_length,
                            "crb_start": crb_start, "crb_length": crb_length, **info})

    def shared(direction: str, channel: str, alloc: dict[str, Any], bwp: dict[str, Any], info: dict[str, Any],
               vrb_origin: int | None = None) -> None:
        rbs = alloc.get("rbs") or {}
        sym_start, sym_length = alloc.get("sym_start", 0), alloc.get("sym_length", 0)
        if rbs.get("type") == "VrbAlloc":
            origin = bwp["crb_start"] if vrb_origin is None else vrb_origin
            first = (origin + rbs["vrb_start"], rbs["vrb_length"])
            hop = rbs.get("vrb_second_hop_start")
            if hop is None:
                add(direction, channel, sym_start, sym_length, [first], info)
            else:
                half = sym_length // 2
                add(direction, channel, sym_start, half, [first], info)
                add(direction, channel, sym_start + half, sym_length - half, [(origin + hop, rbs["vrb_length"])], info)
        elif rbs.get("type") == "RbgAlloc":
            add(direction, channel, sym_start, sym_length, _rbg_crbs(rbs["bitmap"], rbs["nof_rbgs"], bwp), info)

    dl, ul = cell.dl_bwp, cell.ul_bwp
    origins = _VrbOrigins(decision.get("dl_pdcchs") or [], cell)
    for i, p in enumerate(decision.get("ue_pdschs") or []):
        cw = (p.get("codewords") or [{}])[0]
        shared("DL", "PDSCH", p, dl, {"item": ["ue_pdschs", i], "rnti": p["rnti"], "harq_id": p["harq_id"], "mcs": cw.get("mcs_index"),
                                      "tbs": cw.get("tb_size_bytes"), "new_data": cw.get("new_data"),
                                      "nof_retxs": p["nof_retxs"], "k1": p["k1"], "ue_index": p["ue_index"]},
               origins.of_rnti(p["rnti"], (C_RNTI_F1_0, TC_RNTI_F1_0, C_RNTI_F1_1)))
    for i, p in enumerate(decision.get("sib_pdschs") or []):
        shared("DL", "SIB", p, dl, {"item": ["sib_pdschs", i], "sib1": p["is_sib1"]}, origins.nth(SI_F1_0, i))
    for i, p in enumerate(decision.get("rar_pdschs") or []):
        shared("DL", "RAR", p, dl, {"item": ["rar_pdschs", i], "rnti": p["rnti"], "grants": len(p.get("grants") or [])},
               origins.of_rnti(p["rnti"], (RA_F1_0,), common=True))
    for i, p in enumerate(decision.get("paging_pdschs") or []):
        shared("DL", "Paging", p, dl, {"item": ["paging_pdschs", i], "paging_ues": len(p.get("paging_ues") or [])},
               origins.nth(P_RNTI_F1_0, i))
    for i, s in enumerate(decision.get("ssbs") or []):
        add("DL", "SSB", s["sym_start"], s["sym_length"], [(s["crbs"]["start"], s["crbs"]["length"])], {"item": ["ssbs", i], "ssb_index": s["ssb_index"]})
    for i, c in enumerate(decision.get("csi_rs") or []):
        add("DL", "CSI-RS", c["symbol0"], 1, [(c["crbs"]["start"], c["crbs"]["length"])], {"item": ["csi_rs", i], "row": c["row"]})
    for i, p in enumerate(decision.get("puschs") or []):
        shared("UL", "PUSCH", p, ul, {"item": ["puschs", i], "rnti": p["rnti"], "harq_id": p["harq_id"], "tbs": p["tb_size_bytes"],
                                      "rv": p["rv_index"], "nof_retxs": p["nof_retxs"], "k2": p["k2"], "ue_index": p["ue_index"]})
    for i, p in enumerate(decision.get("pucchs") or []):
        res = cell.pucch_resources[p["res_idx"]] if p["res_idx"] < len(cell.pucch_resources) else None
        if res is None:
            continue
        nof_prbs = (res.get("format") or {}).get("nof_prbs") or 1
        info = {"item": ["pucchs", i], "rnti": p["rnti"], "format": (res.get("format") or {}).get("type"), "harq_bits": p["nof_bits_harq_ack"],
                "sr_bits": p["nof_bits_sr"], "csi_bits": p["nof_bits_csi1"]}
        start = ul["crb_start"] + res["prb_start"]
        hop = res.get("prb_second_hop_start")
        if hop is None:
            add("UL", "PUCCH", res["sym_start"], res["sym_length"], [(start, nof_prbs)], info)
        else:
            half = res["sym_length"] // 2
            add("UL", "PUCCH", res["sym_start"], half, [(start, nof_prbs)], info)
            add("UL", "PUCCH", res["sym_start"] + half, res["sym_length"] - half, [(ul["crb_start"] + hop, nof_prbs)], info)
    return out


class _VrbOrigins:
    """The CRBs from which the VRBs of the PDSCHs of a slot count, from the DL PDCCHs that schedule them."""

    def __init__(self, pdcchs: list[dict[str, Any]], cell: Cell):
        self.pdcchs = pdcchs
        self.lowest_crb = {cs["id"]: min(r["start"] for r in cs["crbs"]) for cs in cell.coresets if cs.get("crbs")}
        self.common = {ss["id"]: ss["is_common"] for ss in cell.search_spaces}

    def of_rnti(self, rnti: int, dci_types: tuple[int, ...], common: bool = False) -> int | None:
        """The origin of the PDSCH of the PDCCH of an RNTI and of one of dci_types. common: of a common PDSCH."""
        pdcch = next((p for p in self.pdcchs if p["rnti"] == rnti and p["dci_type"] in dci_types), None)
        return self._of(pdcch, common)

    def nth(self, dci_type: int, n: int) -> int | None:
        """The origin of the n-th common PDSCH of a DCI type, scheduled in the order of their PDCCHs."""
        pdcchs = [p for p in self.pdcchs if p["dci_type"] == dci_type]
        return self._of(pdcchs[n] if n < len(pdcchs) else None, True)

    def _of(self, pdcch: dict[str, Any] | None, common: bool) -> int | None:
        """The lowest CRB of the CORESET of a PDCCH of DCI format 1_0 in a common search space, else None for the BWP
        start. A common PDSCH whose PDCCH is not in the slot is taken as scheduled from CORESET#0.
        """
        if pdcch is None:
            return self.lowest_crb.get(0) if common else None
        if pdcch["dci_type"] == C_RNTI_F1_1 or not self.common.get(pdcch["ss_id"], False):
            return None
        return self.lowest_crb.get(pdcch["coreset_id"])


def _rbg_crbs(bitmap: int, nof_rbgs: int, bwp: dict[str, Any]) -> list[tuple[int, int]]:
    """CRB ranges of the RBGs of a bitmap, merged where contiguous. RBG 0 is the most significant of the nof_rbgs bits,
    as OCUDU writes them.
    """
    size = rbg_size(bwp["crb_length"])
    start, end = bwp["crb_start"], bwp["crb_start"] + bwp["crb_length"]
    # The first RBG ends at the next multiple of the RBG size, counted in CRBs.
    first_end = (start // size + 1) * size
    ranges: list[tuple[int, int]] = []
    for i in range(nof_rbgs):
        if not (bitmap >> (nof_rbgs - 1 - i)) & 1:
            continue
        lo = start if i == 0 else first_end + (i - 1) * size
        hi = min(end, first_end if i == 0 else lo + size)
        if ranges and ranges[-1][0] + ranges[-1][1] == lo:
            ranges[-1] = (ranges[-1][0], hi - ranges[-1][0])
        else:
            ranges.append((lo, hi - lo))
    return ranges


def occupancy(rects: list[dict[str, Any]], group_size: int) -> dict[tuple[int, str], float]:
    """Resource elements of the rectangles of a slot in each group of group_size CRBs, by (group, channel), as a
    fraction of the group's elements in a slot.
    """
    out: dict[tuple[int, str], float] = {}
    for r in rects:
        lo, hi = r["crb_start"], r["crb_start"] + r["crb_length"]
        for g in range(lo // group_size, (hi - 1) // group_size + 1):
            overlap = min(hi, (g + 1) * group_size) - max(lo, g * group_size)
            key = (g, r["channel"])
            out[key] = out.get(key, 0.0) + overlap * r["sym_length"] / (group_size * NOF_SYMBOLS)
    return out
