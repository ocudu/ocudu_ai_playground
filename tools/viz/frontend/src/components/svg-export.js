// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

// Vector copy of a uPlot time chart as SVG, from the layout the chart computed: its plot box, scales, and the tick
// positions and labels of its axes. Those are uPlot internals (axis._splits, _values, _pos and _lpos of uPlot 1.6),
// read instead of laying the chart out again, so that the copy matches the chart.

// Font of uPlot axes, which the chart does not set.
const AXIS_FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif';
const AXIS_FONT_SIZE = 12;

/** @param {string} text */
export function escapeXml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" })[c]);
}

/** @param {number} v */
function num(v) {
  return Math.round(v * 10) / 10;
}

/**
 * SVG elements drawing a chart, offset by (ox, oy) CSS pixels.
 * @param {any} u uPlot chart, drawn.
 * @param {number} ox
 * @param {number} oy
 * @param {{axis: string, grid: string, series: string[], lineWidth: number, events: Array<{t: number, color: string}>}} style
 * @param {string} clipId Id of the clip path of the plot area, unique in the document.
 */
export function chartSvg(u, ox, oy, style, clipId) {
  const dpr = devicePixelRatio;
  const left = ox + u.bbox.left / dpr;
  const top = oy + u.bbox.top / dpr;
  const width = u.bbox.width / dpr;
  const height = u.bbox.height / dpr;
  const out = [`<clipPath id="${clipId}"><rect x="${num(left)}" y="${num(top)}" width="${num(width)}" height="${num(height)}"/></clipPath>`];
  const font = `font-family="${escapeXml(AXIS_FONT_FAMILY)}" font-size="${AXIS_FONT_SIZE}"`;

  u.axes.forEach((axis, i) => {
    if (!axis.show || !axis._show || !axis._splits) return;
    const scale = i === 0 ? "x" : axis.scale ?? "y";
    const horizontal = axis.side % 2 === 0;
    const tickSize = axis.ticks?.show ? axis.ticks.size : 0;
    const pos = (horizontal ? oy : ox) + axis._pos;
    const dir = axis.side === 0 || axis.side === 3 ? -1 : 1;
    const grid = [];
    const ticks = [];
    const labels = [];
    axis._splits.forEach((split, k) => {
      const at = (horizontal ? left : top) + u.valToPos(split, scale);
      if (horizontal) {
        grid.push(`M${num(at)} ${num(top)}V${num(top + height)}`);
        ticks.push(`M${num(at)} ${num(pos)}v${num(dir * tickSize)}`);
      } else {
        grid.push(`M${num(left)} ${num(at)}H${num(left + width)}`);
        ticks.push(`M${num(pos)} ${num(at)}h${num(dir * tickSize)}`);
      }
      const text = axis._values?.[k];
      if (text == null) return;
      const offset = pos + dir * (tickSize + axis.gap);
      labels.push(
        horizontal
          ? `<text x="${num(at)}" y="${num(offset)}" text-anchor="middle" dominant-baseline="hanging">${escapeXml(text)}</text>`
          : `<text x="${num(offset)}" y="${num(at)}" text-anchor="${dir < 0 ? "end" : "start"}" dominant-baseline="middle">${escapeXml(text)}</text>`,
      );
    });
    if (axis.grid?.show !== false) out.push(`<path d="${grid.join("")}" stroke="${style.grid}" stroke-width="1" fill="none"/>`);
    if (tickSize) out.push(`<path d="${ticks.join("")}" stroke="${style.grid}" stroke-width="1" fill="none"/>`);
    out.push(`<g fill="${style.axis}" ${font}>${labels.join("")}</g>`);
    if (axis.label) {
      const at = (horizontal ? oy : ox) + axis._lpos + dir * axis.labelGap;
      const label = escapeXml(axis.label);
      out.push(
        horizontal
          ? `<text x="${num(left + width / 2)}" y="${num(at)}" text-anchor="middle" fill="${style.axis}" font-weight="bold" ${font}>${label}</text>`
          : `<text transform="translate(${num(at)} ${num(top + height / 2)}) rotate(${dir < 0 ? -90 : 90})" text-anchor="middle" dominant-baseline="${dir < 0 ? "text-after-edge" : "text-before-edge"}" fill="${style.axis}" font-weight="bold" ${font}>${label}</text>`,
      );
    }
  });

  const xs = u.data[0];
  const series = [];
  // Points get a clip area wider by their size, like uPlot gives them, so that points on the edges stay whole.
  const pointGroups = [];
  let pointMargin = 0;
  for (let i = 1; i < u.series.length; i++) {
    const s = u.series[i];
    if (!s.show) continue;
    const ys = u.data[i];
    const color = style.series[i - 1];
    const points = [];
    let d = "";
    // Gaps are bridged, as the chart does with spanGaps.
    for (let k = 0; k < xs.length; k++) {
      if (ys[k] == null) continue;
      const x = left + u.valToPos(xs[k], "x");
      const y = top + u.valToPos(ys[k], s.scale ?? "y");
      d += `${d ? "L" : "M"}${num(x)} ${num(y)}`;
      points.push([x, y]);
    }
    const dash = s.dash?.length ? ` stroke-dasharray="${s.dash.join(" ")}"` : "";
    if (d) series.push(`<path d="${d}" stroke="${color}" stroke-width="${style.lineWidth}" fill="none" stroke-linejoin="round"${dash}/>`);
    // uPlot draws the points of a series when they are spaced enough, with its own test and sizes.
    const p = s.points;
    const shown = typeof p?.show === "function" ? p.show(u, i) : p?.show;
    if (shown && points.length) {
      const size = typeof p.size === "function" ? p.size(u, i) : p.size;
      const r = num((size - p.width) / 2);
      const dots = points.map(([x, y]) => `<circle cx="${num(x)}" cy="${num(y)}" r="${r}"/>`).join("");
      pointGroups.push(`<g fill="#ffffff" stroke="${color}" stroke-width="${num(p.width)}">${dots}</g>`);
      pointMargin = Math.max(pointMargin, size);
    }
  }
  const markers = style.events
    .map((ev) => ({ ...ev, x: left + u.valToPos(ev.t, "x") }))
    .filter((ev) => ev.x >= left && ev.x <= left + width)
    .map((ev) => `<path d="M${num(ev.x)} ${num(top)}V${num(top + height)}" stroke="${ev.color}" stroke-width="1" stroke-dasharray="4 4" opacity="0.75"/>`);
  out.push(`<g clip-path="url(#${clipId})">${series.join("")}${markers.join("")}</g>`);
  if (pointGroups.length) {
    const m = pointMargin;
    out.push(`<clipPath id="${clipId}-points"><rect x="${num(left - m)}" y="${num(top - m)}" width="${num(width + 2 * m)}" height="${num(height + 2 * m)}"/></clipPath>`);
    out.push(`<g clip-path="url(#${clipId}-points)">${pointGroups.join("")}</g>`);
  }
  return out.join("\n");
}
