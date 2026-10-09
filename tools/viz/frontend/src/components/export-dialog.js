// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import uPlot from "uplot";
import { getJSON } from "../api.js";
import { MAX_LEGEND_SERIES, TIME_TICK_SPACE, chartSeries, cssVar, plotData, seriesColor, timeTicks, utcDate, valueAxes } from "./chart-utils.js";
import { chartSvg, escapeXml } from "./svg-export.js";

// Size of the image, in CSS pixels, when the dialog opens.
const DEFAULT_WIDTH = 1000;
const DEFAULT_HEIGHT = 420;
const MIN_WIDTH = 300;
const MIN_HEIGHT = 200;
// Delay before fetching the series again after a resize, to coalesce the resize events.
const REFETCH_DELAY_MS = 300;
// Delay before releasing the image of a saved file.
const REVOKE_DELAY_MS = 60_000;
// Time the Copy button says the image was copied.
const COPIED_MS = 1500;

/**
 * File name of an exported plot, without unsafe characters.
 * @param {string[]} parts
 */
function fileName(parts, extension) {
  return parts.filter(Boolean).join("_").replace(/[^\w.-]+/g, "_") + extension;
}

/**
 * Downloads a blob as a file.
 * @param {Blob} blob
 * @param {string} name
 */
function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  // Released later, since revoking it at once can cancel the download.
  setTimeout(() => URL.revokeObjectURL(url), REVOKE_DELAY_MS);
}

export default {
  name: "ExportDialog",
  props: {
    // Query of /api/series of the plot, without its width.
    params: { type: Object, required: true },
    // Field of the second metric of the plot, or null.
    field2: { type: String, default: null },
    // Shift from source time to display time, and the time range shown, in display time.
    shift: { type: Number, default: 0 },
    view: { type: Object, default: null },
    timeMode: { type: String, required: true },
    title: { type: String, required: true },
    // Parts of the name of the saved file, e.g. the file, dataset and field.
    nameParts: { type: Array, required: true },
    // Event markers of the plot, in display time.
    events: { type: Array, default: () => [] },
  },
  emits: ["close"],
  data() {
    return {
      maxLegendSeries: MAX_LEGEND_SERIES,
      width: DEFAULT_WIDTH,
      height: DEFAULT_HEIGHT,
      // Value series of the chart, see plotData().
      series: [],
      error: "",
      loading: false,
      ready: false,
      copied: false,
    };
  },
  watch: {
    // Events can arrive after the chart is drawn, e.g. when their category was just shown.
    events() {
      this.chart?.redraw(false, true);
    },
    width() {
      this.resized();
    },
    height() {
      this.resized();
    },
  },
  created() {
    // Not reactive: drawing state owned by the chart.
    this.chart = null;
    this.fetchedWidth = 0;
    this.refetchTimer = null;
  },
  mounted() {
    this.resizeObserver = new ResizeObserver(() => {
      // Dragging the corner of the frame resizes it, which the size fields follow.
      const frame = this.$refs.frame;
      this.width = Math.max(MIN_WIDTH, Math.round(frame.offsetWidth));
      this.height = Math.max(MIN_HEIGHT, Math.round(frame.offsetHeight));
    });
    this.resizeObserver.observe(this.$refs.frame);
    this.onKey = (e) => {
      if (e.key === "Escape") this.$emit("close");
    };
    window.addEventListener("keydown", this.onKey);
    this.load();
  },
  beforeUnmount() {
    this.resizeObserver?.disconnect();
    window.removeEventListener("keydown", this.onKey);
    clearTimeout(this.refetchTimer);
    this.chart?.destroy();
  },
  methods: {
    /** Fetches the series at the width of the chart, so that a wider image is not stretched from fewer points. */
    async load() {
      this.loading = true;
      const width = Math.max(100, Math.round(this.$refs.chart.clientWidth));
      try {
        const [res, res2] = await Promise.all([
          getJSON("/api/series", { ...this.params, width }),
          this.field2 ? getJSON("/api/series", { ...this.params, field: this.field2, width }) : null,
        ]);
        this.error = "";
        this.fetchedWidth = width;
        this.render(res, res2);
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    async render(res, res2) {
      const { data, series, unit, unit2 } = plotData(res, res2, this.shift, this.params.field, this.field2);
      this.series = series;
      // The legend takes its height first, which the chart leaves to it.
      await this.$nextTick();
      this.chart?.destroy();
      this.chart = this.createChart(data, series, unit, unit2);
      this.ready = true;
    },

    /** Chart of the plot in the light theme of the frame, without interactions or legend, which the frame shows. */
    createChart(data, series, unit, unit2) {
      const el = this.$refs.frame;
      const axisColor = cssVar("--fg-muted", el);
      const gridColor = cssVar("--grid", el);
      const axis = { stroke: axisColor, grid: { stroke: gridColor, width: 1 }, ticks: { stroke: gridColor, width: 1 } };
      const absolute = this.timeMode === "absolute";
      const xAxis = absolute ? { ...axis, values: timeTicks, space: TIME_TICK_SPACE } : { ...axis };
      const opts = {
        width: this.$refs.chart.clientWidth,
        height: this.chartHeight(),
        scales: { x: { time: absolute, min: this.view?.min, max: this.view?.max } },
        tzDate: utcDate,
        legend: { show: false },
        cursor: { show: false },
        series: [{}, ...chartSeries(series, 1.5, el)],
        axes: [xAxis, ...valueAxes(axis, unit, unit2, this.params.field, this.field2)],
        hooks: { draw: [(u) => this.drawEvents(u)] },
      };
      return new uPlot(opts, data, this.$refs.chart);
    },

    /** Height left to the chart in the frame, below the title and above the legend. */
    chartHeight() {
      const used = this.$refs.title.offsetHeight + this.$refs.legend.offsetHeight;
      return Math.max(100, this.height - used);
    },

    /** Draws the event markers of the plot as dashed vertical lines, like the plot does. */
    drawEvents(u) {
      const { ctx, bbox } = u;
      const el = this.$refs.frame;
      const colors = {};
      const dpr = devicePixelRatio;
      ctx.save();
      ctx.lineWidth = Math.max(1, dpr);
      ctx.globalAlpha = 0.75;
      for (const ev of this.events) {
        const x = Math.round(u.valToPos(ev.t, "x", true));
        if (x < bbox.left || x > bbox.left + bbox.width) continue;
        ctx.strokeStyle = colors[ev.category] ??= cssVar(`--ev-${ev.category}`, el);
        ctx.setLineDash([4 * dpr, 4 * dpr]);
        ctx.beginPath();
        ctx.moveTo(x, bbox.top);
        ctx.lineTo(x, bbox.top + bbox.height);
        ctx.stroke();
      }
      ctx.restore();
    },

    /** Resizes the chart to the frame, and fetches the series again once the chart is notably wider. */
    async resized() {
      await this.$nextTick();
      if (!this.chart) return;
      this.chart.setSize({ width: this.$refs.chart.clientWidth, height: this.chartHeight() });
      clearTimeout(this.refetchTimer);
      if (this.$refs.chart.clientWidth > this.fetchedWidth * 1.2) {
        this.refetchTimer = setTimeout(() => this.load(), REFETCH_DELAY_MS);
      }
    },

    /** Saves the image as a PNG file. */
    async savePng() {
      download(await this.renderPng(), fileName(this.nameParts, ".png"));
    },

    /** Saves the image as an SVG file: vector lines and text, laid out like the PNG. */
    saveSvg() {
      download(new Blob([this.renderSvg()], { type: "image/svg+xml" }), fileName(this.nameParts, ".svg"));
    },

    /** The frame as an SVG document: its title, chart and legend, where the frame shows them, on white. */
    renderSvg() {
      const frame = this.$refs.frame;
      const box = frame.getBoundingClientRect();
      const at = (el) => {
        const r = el.getBoundingClientRect();
        return { x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height };
      };
      const text = (el, value) => {
        const style = getComputedStyle(el);
        const r = at(el);
        return `<text x="${r.x}" y="${r.y + r.h / 2}" dominant-baseline="middle" fill="${style.color}" font-family="${escapeXml(style.fontFamily)}" font-size="${style.fontSize}" font-weight="${style.fontWeight}">${escapeXml(value)}</text>`;
      };
      const parts = [`<rect width="100%" height="100%" fill="#ffffff"/>`, text(this.$refs.titleText, this.title)];
      // The chart canvas starts at the origin of the chart layout, in which uPlot places its plot box and axes.
      const canvas = at(this.$refs.chart.querySelector("canvas"));
      const style = {
        axis: cssVar("--fg-muted", frame),
        grid: cssVar("--grid", frame),
        series: this.series.map((s) => seriesColor(s.color, frame)),
        lineWidth: 1.5,
        events: this.events.map((ev) => ({ t: ev.t, color: cssVar(`--ev-${ev.category}`, frame) })),
      };
      parts.push(chartSvg(this.chart, canvas.x, canvas.y, style, "plot-area"));
      for (const item of this.$refs.legend.querySelectorAll(".export-legend-item")) {
        const swatch = item.querySelector(".swatch");
        const r = at(swatch);
        parts.push(`<rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" fill="${getComputedStyle(swatch).backgroundColor}"/>`);
        const label = item.querySelector(".label");
        parts.push(text(label, label.textContent));
      }
      const width = Math.round(box.width);
      const height = Math.round(box.height);
      return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">\n${parts.join("\n")}\n</svg>\n`;
    },

    /** Puts the image on the clipboard, as a PNG. */
    async copyPng() {
      try {
        // The image is given as a promise, so that the copy keeps the user gesture while the image is drawn.
        await navigator.clipboard.write([new ClipboardItem({ "image/png": this.renderPng() })]);
        this.error = "";
        this.copied = true;
        setTimeout(() => {
          this.copied = false;
        }, COPIED_MS);
      } catch (e) {
        this.error = `Could not copy the image: ${e.message}`;
      }
    },

    /** Draws the frame as a PNG: its title, chart and legend, where the frame shows them, on white. */
    renderPng() {
      const frame = this.$refs.frame;
      const box = frame.getBoundingClientRect();
      const dpr = devicePixelRatio;
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(box.width * dpr);
      canvas.height = Math.round(box.height * dpr);
      const ctx = canvas.getContext("2d");
      ctx.scale(dpr, dpr);
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, box.width, box.height);

      const at = (el) => {
        const r = el.getBoundingClientRect();
        return { x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height };
      };
      const drawText = (el, text) => {
        const style = getComputedStyle(el);
        const r = at(el);
        ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        ctx.fillStyle = style.color;
        ctx.textBaseline = "middle";
        ctx.fillText(text, r.x, r.y + r.h / 2);
      };

      drawText(this.$refs.titleText, this.title);
      for (const c of this.$refs.chart.querySelectorAll("canvas")) {
        const r = at(c);
        ctx.drawImage(c, r.x, r.y, r.w, r.h);
      }
      for (const item of this.$refs.legend.querySelectorAll(".export-legend-item")) {
        const swatch = item.querySelector(".swatch");
        const r = at(swatch);
        ctx.fillStyle = getComputedStyle(swatch).backgroundColor;
        ctx.fillRect(r.x, r.y, r.w, r.h);
        const label = item.querySelector(".label");
        drawText(label, label.textContent);
      }

      return new Promise((resolve, reject) => {
        canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("the image could not be drawn"))), "image/png");
      });
    },

    seriesColor(i) {
      return seriesColor(i, this.$refs.frame);
    },
  },
  template: `
    <div class="modal-backdrop">
      <section class="modal export-dialog" role="dialog" aria-label="Save the plot">
        <header class="panel-bar">
          <strong>Save the plot</strong>
          <label class="inline">width <input v-model.number.lazy="width" type="number" :min="${MIN_WIDTH}" step="10" /></label>
          <label class="inline">height <input v-model.number.lazy="height" type="number" :min="${MIN_HEIGHT}" step="10" /></label>
          <span class="muted">px, or drag the corner of the image</span>
          <span v-if="loading" class="muted">loading</span>
          <span v-if="error" class="error">{{ error }}</span>
          <span class="status"></span>
          <button :disabled="!ready || loading" title="Copy the image to the clipboard, e.g. to paste it in a chat or slide" @click="copyPng">{{ copied ? "Copied" : "Copy" }}</button>
          <button :disabled="!ready || loading" title="Save the image as an SVG file, with vector lines and text" @click="saveSvg">Save SVG</button>
          <button class="primary" :disabled="!ready || loading" title="Save the image as a PNG file" @click="savePng">Save PNG</button>
          <button class="icon" title="Close" @click="$emit('close')">✕</button>
        </header>
        <div class="export-stage">
          <div ref="frame" class="export-frame theme-light" :style="{ width: width + 'px', height: height + 'px' }">
            <div ref="title" class="export-title"><span ref="titleText">{{ title }}</span></div>
            <div ref="chart" class="export-chart"></div>
            <div ref="legend" class="export-legend">
              <span v-for="(s, i) in series.slice(0, maxLegendSeries)" :key="i" class="export-legend-item">
                <span class="swatch" :style="{ background: seriesColor(s.color) }"></span><span class="label">{{ s.label }}</span>
              </span>
              <span v-if="series.length > maxLegendSeries" class="export-legend-item">
                <span class="swatch" style="width: 0"></span><span class="label">+{{ series.length - maxLegendSeries }} more</span>
              </span>
            </div>
          </div>
        </div>
      </section>
    </div>
  `,
};
