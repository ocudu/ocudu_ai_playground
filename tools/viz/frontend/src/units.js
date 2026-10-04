// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

// Display units per canonical unit, largest first.
const SCALES = {
  us: [[1e6, "s"], [1e3, "ms"], [1, "us"]],
  bps: [[1e9, "Gbps"], [1e6, "Mbps"], [1e3, "kbps"], [1, "bps"]],
  bytes: [[1e9, "GB"], [1e6, "MB"], [1e3, "kB"], [1, "B"]],
};

/**
 * Picks the display unit for values of the given canonical unit and magnitude.
 * @param {string | null} unit
 * @param {number} maxAbs
 * @returns {{divisor: number, label: string}}
 */
export function displayUnit(unit, maxAbs) {
  const scales = SCALES[unit];
  if (!scales) return { divisor: 1, label: unit || "" };
  for (const [divisor, label] of scales) {
    if (maxAbs >= divisor) return { divisor, label };
  }
  const [divisor, label] = scales[scales.length - 1];
  return { divisor, label };
}

/**
 * Formats a number compactly for display, with an en dash for missing values.
 * @param {number | null} v
 */
export function formatStat(v) {
  if (v == null) return "\u2013";
  if (v !== 0 && (Math.abs(v) >= 1e6 || Math.abs(v) < 1e-3)) return v.toExponential(3);
  return String(Number(v.toPrecision(5)));
}
