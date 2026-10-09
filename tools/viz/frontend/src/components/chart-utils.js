// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import uPlot from "uplot";
import { displayUnit } from "../units.js";

// Key of the cursor shared by the time charts of a page.
export const CURSOR_SYNC_KEY = "ocudu-viz";
// Minimum pixels between absolute time ticks, so that HH:mm:ss.fff labels do not overlap.
export const TIME_TICK_SPACE = 110;
// Series listed in legends, as many as the statistics of the server list. Charts draw all.
export const MAX_LEGEND_SERIES = 16;

/**
 * Text of an event under the cursor: its type and message, and for an event of repeated lines, their count and span.
 * @param {{type: string, text: string, count?: number | null, span?: number | null}} ev
 */
export function eventText(ev) {
  const span = ev.span ?? 0;
  const over = span < 1 ? `${Math.round(span * 1000)} ms` : `${span.toFixed(1)} s`;
  const repeated = ev.count > 1 ? ` (×${ev.count} over ${over})` : "";
  return `${ev.type}: ${ev.text}${repeated}`;
}

/** Hides the legend rows of a uPlot chart past the first MAX_LEGEND_SERIES series. */
export function capLegend(chart) {
  // Row 0 is the one of the x values.
  chart.root.querySelectorAll(".u-legend .u-series").forEach((row, i) => {
    if (i > MAX_LEGEND_SERIES) row.style.display = "none";
  });
}

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
 * @typedef {{unit: string | null, series: Array<{label: string, split: any, t: number[], v: number[], record: number[]}>}} SeriesResponse
 * @typedef {{label: string, color: number, dash: boolean, scale: string, field: string}} SeriesInfo
 */

/**
 * Chart data of the /api/series responses of one metric, or of two: the series aligned on the union of their times,
 * shifted to display time and scaled to a display unit, with their records and how to draw each.
 *
 * With a second metric, its series follow those of the first, dashed, in the color of the series of the first of the
 * same split value. They share the scale ("y") and unit of the first when both have the same unit, and else have
 * their own ("y2", unit2). Labels then name the field, e.g. "ul_brate rnti=0x4601".
 * @param {SeriesResponse} res
 * @param {SeriesResponse | null} res2
 * @param {number} shift
 * @param {string} field
 * @param {string | null} field2
 */
export function plotData(res, res2, shift, field, field2 = null) {
  const both = [...res.series, ...(res2?.series ?? [])];
  const tables = both.map((s) => [s.t.map((t) => t + shift), s.v, s.record]);
  // Series have their own timestamps, so they are aligned on the union of them.
  const joined = tables.length ? uPlot.join(tables) : [[]];
  const shared = res2 == null || (res.unit != null && res.unit === res2.unit);
  const maxAbs = (series) => series.reduce((m, s) => s.v.reduce((a, v) => Math.max(a, Math.abs(v)), m), 0);
  const unit = displayUnit(res.unit, maxAbs(shared ? both : res.series));
  const unit2 = res2 == null || shared ? null : displayUnit(res2.unit, maxAbs(res2.series));
  const named = (f, s) => (res2 == null || s.label === f ? s.label : `${f} ${s.label}`);
  /** @type {SeriesInfo[]} */
  const series = [
    ...res.series.map((s, i) => ({ label: named(field, s), color: i, dash: false, scale: "y", field })),
    ...(res2?.series ?? []).map((s, j) => {
      const same = res.series.findIndex((f) => f.split === s.split);
      return { label: named(field2, s), color: same >= 0 ? same : res.series.length + j, dash: true, scale: unit2 ? "y2" : "y", field: field2 };
    }),
  ];
  const data = [joined[0]];
  const records = [];
  for (let i = 0; i < tables.length; i++) {
    const divisor = (series[i].scale === "y2" ? unit2 : unit).divisor;
    data.push(joined[1 + 2 * i].map((v) => (v == null ? v : v / divisor)));
    records.push(joined[2 + 2 * i]);
  }
  return { data, series, labels: series.map((s) => s.label), unit, unit2, records };
}

/**
 * uPlot options of the value series of plotData().
 * @param {SeriesInfo[]} series
 * @param {number} width Line width.
 * @param {Element} [el] Element whose theme gives the colors.
 */
export function chartSeries(series, width, el) {
  return series.map((s) => ({ label: s.label, stroke: seriesColor(s.color, el), width, spanGaps: true, scale: s.scale, dash: s.dash ? [6, 4] : undefined }));
}

/**
 * uPlot axes of the values of plotData(): the left one of the unit of the first metric, and a right one for the
 * second metric when it has a unit of its own. Two axes are labelled with their field too, e.g. "dl_brate [Mbps]".
 * @param {Record<string, any>} axis Common axis options.
 * @param {{label: string}} unit
 * @param {{label: string} | null} unit2
 * @param {string} field
 * @param {string | null} field2
 */
export function valueAxes(axis, unit, unit2, field, field2) {
  if (!unit2) return [{ ...axis, label: unit.label, size: 60 }];
  const label = (f, u) => f + (u.label ? ` [${u.label}]` : "");
  return [
    { ...axis, label: label(field, unit), size: 60 },
    { ...axis, scale: "y2", side: 1, label: label(field2, unit2), size: 60, grid: { show: false } },
  ];
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
