// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import uPlot from "uplot";
import { displayUnit } from "../units.js";

// Key of the cursor shared by the time charts of a page.
export const CURSOR_SYNC_KEY = "ocudu-viz";
// Minimum pixels between absolute time ticks, so that HH:mm:ss.fff labels do not overlap.
export const TIME_TICK_SPACE = 110;

const fmtMs = uPlot.fmtDate("{HH}:{mm}:{ss}.{fff}");
const fmtSec = uPlot.fmtDate("{HH}:{mm}:{ss}");
const fmtMin = uPlot.fmtDate("{HH}:{mm}");
export const fmtFull = uPlot.fmtDate("{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}.{fff}");

/** @param {number} ts */
export function utcDate(ts) {
  return uPlot.tzDate(new Date(ts * 1e3), "Etc/UTC");
}

/**
 * 24h UTC tick labels, with sub-second digits when zoomed in.
 * @param {any} u
 * @param {number[]} splits
 * @param {number} axisIdx
 * @param {number} space
 * @param {number} incr
 */
export function timeTicks(u, splits, axisIdx, space, incr) {
  const fmt = incr < 1 ? fmtMs : incr < 60 ? fmtSec : fmtMin;
  return splits.map((ts) => fmt(utcDate(ts)));
}

/**
 * Value of a CSS variable, as the page has it or, given an element, as that element has it.
 * @param {string} name
 * @param {Element} [el]
 */
export function cssVar(name, el = document.documentElement) {
  return getComputedStyle(el).getPropertyValue(name).trim();
}

// Number of series colors defined by the theme, as CSS variables --s0 to --s9.
const NOF_SERIES_COLORS = 10;

/**
 * Color of the series at index i.
 * @param {number} i
 * @param {Element} [el] Element whose theme gives the color, the page by default.
 */
export function seriesColor(i, el) {
  return cssVar(`--s${i % NOF_SERIES_COLORS}`, el);
}

/**
 * Chart data of a /api/series response: the series aligned on the union of their times, shifted to display time and
 * scaled to a display unit, with their labels and records.
 * @param {{unit: string | null, series: Array<{label: string, t: number[], v: number[], record: number[]}>}} res
 * @param {number} shift
 */
export function seriesData(res, shift) {
  const tables = res.series.map((s) => [s.t.map((t) => t + shift), s.v, s.record]);
  // Series have their own timestamps, so they are aligned on the union of them.
  const joined = tables.length ? uPlot.join(tables) : [[]];
  const values = [];
  const records = [];
  for (let i = 0; i < tables.length; i++) {
    values.push(joined[1 + 2 * i]);
    records.push(joined[2 + 2 * i]);
  }
  let maxAbs = 0;
  for (const s of res.series) for (const v of s.v) maxAbs = Math.max(maxAbs, Math.abs(v));
  const unit = displayUnit(res.unit, maxAbs);
  const scaled = values.map((col) => col.map((v) => (v == null ? v : v / unit.divisor)));
  return { data: [joined[0], ...scaled], labels: res.series.map((s) => s.label), unit, records };
}

/**
 * Formats a time of a chart for the cursor readout.
 * @param {number} t
 * @param {string} timeMode "absolute" or "relative".
 */
export function formatTime(t, timeMode) {
  return timeMode === "absolute" ? fmtFull(utcDate(t)) : `${t.toFixed(3)} s`;
}

/**
 * Makes a time chart pan with Shift+drag, reporting the new range with onZoom (null to reset on double-click), and
 * calls onClick for clicks that do not end a drag. The mouse wheel is left to scroll the page.
 * @param {any} chart
 * @param {(range: {min: number, max: number} | null) => void} onZoom
 * @param {() => void} onClick
 */
export function attachZoomPan(chart, onZoom, onClick) {
  const over = chart.over;
  const xRange = () => ({ min: chart.scales.x.min, max: chart.scales.x.max });

  // Shift+drag pans. Registered as capture to run before the uPlot drag-to-zoom handler.
  over.addEventListener("mousedown", (e) => {
    if (!e.shiftKey || e.button !== 0) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    const start = xRange();
    const startX = e.clientX;
    const valPerPx = (start.max - start.min) / over.clientWidth;
    const onMove = (ev) => {
      const dv = (ev.clientX - startX) * valPerPx;
      onZoom({ min: start.min - dv, max: start.max - dv });
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, { capture: true });

  let downX = null;
  over.addEventListener("mousedown", (e) => { downX = e.clientX; });
  over.addEventListener("click", (e) => {
    // Clicks ending a drag-to-zoom are not clicks on the chart content.
    if (downX === null || Math.abs(e.clientX - downX) > 3) return;
    onClick();
  });
  over.addEventListener("dblclick", () => onZoom(null));
}

/**
 * uPlot hook that reports a drag selection as a zoom range and clears the selection.
 * @param {(range: {min: number, max: number}) => void} onZoom
 */
export function selectToZoom(onZoom) {
  return (u) => {
    if (u.select.width > 2) {
      onZoom({ min: u.posToVal(u.select.left, "x"), max: u.posToVal(u.select.left + u.select.width, "x") });
    }
    u.setSelect({ left: 0, top: 0, width: 0, height: 0 }, false);
  };
}
