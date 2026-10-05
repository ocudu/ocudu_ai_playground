# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Synthetic OCUDU logs for the tests."""

from datetime import datetime, timedelta
from pathlib import Path

# Timestamp of the first metrics lines.
START = datetime(2026, 6, 29, 14, 10, 0)


def _ts(seconds: float) -> str:
    return (START + timedelta(seconds=seconds)).isoformat(timespec="microseconds")


def write_log(path: Path, nof_seconds: int = 10, nof_ues: int = 2, executors: bool = False) -> Path:
    """Writes a log with one MAC and one Scheduler UE line per UE per second, among other lines.

    Metrics start at START. The log starts 2 s before the first and ends 2 s after the last metrics lines.

    With executors, it also writes one line per second for executors "cell_exec" and "du_ctrl_exec".
    """
    lines = [f"{_ts(-2)} [GNB     ] [I] Built in Release mode\n"]
    for s in range(nof_seconds):
        ts = _ts(s)
        lines.append(f"{ts} [SCHED   ] [I] [  {s}.0] Slot decisions\n")
        lines.append(f"{ts} [METRICS ] MAC cell pci=1 metrics: nof_slots=2000 wall_clock_latency=[avg={s}usec max={10 * s}usec max_slot={s}.3]\n")
        for ue in range(nof_ues):
            lines.append(
                f"{ts} [METRICS ] Scheduler UE ue={ue} pci=1 rnti=0x46{ue:02x} metrics: cqi=15 dl_brate={s}kbps "
                f"dl_bs=1.2k pusch_snr_db={20 + ue}.5 ta=n/a max_crc_delay=2.5ms\n"
            )
        if executors:
            for i, name in enumerate(("cell_exec", "du_ctrl_exec")):
                lines.append(
                    f'{ts} [METRICS ] Executor metrics "{name}": nof_executes={100 * (i + 1) + s} nof_defers=0 '
                    f"enqueue_avg=1usec enqueue_max=5usec task_avg={10 * (i + 1)}usec task_max=50usec cpu_load=1.5% "
                    f"nof_vol_ctxt_switch=0 nof_invol_ctxt_switch=0\n"
                )
    lines.append(f"{_ts(nof_seconds + 1)} [GNB     ] [I] Stopped\n")
    lines.append("  continuation line without a timestamp\n")
    path.write_text("".join(lines))
    return path
