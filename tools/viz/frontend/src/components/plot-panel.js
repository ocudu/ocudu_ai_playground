// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import uPlot from "uplot";
import { getJSON } from "../api.js";
import { displayUnit, formatStat } from "../units.js";
import { CURSOR_SYNC_KEY, TIME_TICK_SPACE, attachZoomPan, cssVar, fmtFull, formatTime, selectToZoom, timeTicks, utcDate } from "./chart-utils.js";

// Distance in pixels within which the cursor is on an event marker.
const EVENT_HIT_PX = 5;
// Number of series colors defined by the theme, as CSS variables --s0 to --s9.
const NOF_SERIES_COLORS = 10;
const CHART_HEIGHT = 260;
const steppedPath = uPlot.paths.stepped({ align: 1 });
// Delay before fetching after the view changes, to coalesce pan events.
const FETCH_DELAY_MS = 120;
// Split values listed in the split value picker.
const MAX_LISTED_SPLITS = 300;
// Dataset and field of new plots, when their source has them.
const DEFAULT_DATASET = "sched";
const DEFAULT_FIELD = "total_dl_brate";

/** @param {number} i */
function seriesColor(i) {
  return cssVar(`--s${i % NOF_SERIES_COLORS}`);
}

/**
 * Index of the nearest non-null entry of arr to idx, or -1.
 * @param {Array<any>} arr
 * @param {number} idx
 */
function nearestDefined(arr, idx) {
  for (let d = 0; d < arr.length; d++) {
    if (arr[idx - d] != null) return idx - d;
    if (arr[idx + d] != null) return idx + d;
  }
  return -1;
}

export default {
  name: "PlotPanel",
  props: {
    plot: { type: Object, required: true },
    sources: { type: Array, required: true },
    view: { type: Object, default: null },
    shifts: { type: Array, required: true },
    timeMode: { type: String, required: true },
    themeVersion: { type: Number, default: 0 },
    // Whether the panel shows a source selector, which is not needed when the source is fixed, e.g. by a tab.
    showSource: { type: Boolean, default: true },
    // Sources the panel may show, e.g. the sources of its tab, or all sources when null.
    choices: { type: Array, default: null },
    // Events drawn as markers on time series, in display time, each with t, source, record, category, type and text.
    events: { type: Array, default: () => [] },
  },
  emits: ["zoom", "remove", "select-record"],
  data() {
    return {
      loading: false,
      error: "",
      downsampled: false,
      totalSplits: 0,
      nofSeries: 0,
      splitOptions: [],
      instanceOptions: [],
      splitFilter: "",
      filterDraft: this.plot.filter,
      stats: [],
      statsSampled: false,
      unit: { divisor: 1, label: "" },
      labels: [],
      cursorText: "",
      // Event under the cursor, shown with the cursor readout.
      cursorEvent: null,
    };
  },
  computed: {
    source() {
      return this.sources[this.plot.source];
    },
    datasets() {
      return this.source ? this.source.datasets.filter((d) => d.fields.some((f) => f.type === "number")) : [];
    },
    dataset() {
      return this.datasets.find((d) => d.name === this.plot.dataset);
    },
    numericFields() {
      return this.dataset ? this.dataset.fields.filter((f) => f.type === "number" && !this.dataset.context.includes(f.name)) : [];
    },
    splitFields() {
      return this.dataset ? this.dataset.context : [];
    },
    shift() {
      return this.shifts[this.plot.source] || 0;
    },
    listedSplits() {
      const filter = this.splitFilter.trim();
      const values = filter ? this.splitOptions.filter((v) => String(v).includes(filter)) : this.splitOptions;
      return values.slice(0, MAX_LISTED_SPLITS);
    },
    statsRows() {
      return this.stats.map((s) => {
        const idx = this.labels.indexOf(s.label);
        // Read after a theme change, which changes the series colors.
        void this.themeVersion;
        const color = idx >= 0 ? seriesColor(idx) : "transparent";
        const scale = (v) => formatStat(v == null ? v : v / this.unit.divisor);
        return { label: s.label, color, count: s.count.toLocaleString(), min: scale(s.min), mean: scale(s.mean), p50: scale(s.p50), p95: scale(s.p95), p99: scale(s.p99), max: scale(s.max) };
      });
    },
    filterDirty() {
      return this.filterDraft.trim() !== this.plot.filter;
    },
    splitSummary() {
      if (this.plot.splitValues.length) return `${this.plot.splitValues.length} selected`;
      if (this.totalSplits > this.nofSeries) return `first ${this.nofSeries} of ${this.totalSplits}`;
      return "all";
    },
  },
  watch: {
    "plot.source"() {
      const dataset = this.defaultDataset();
      // An unchanged dataset name does not trigger its watcher, but the instances differ per source.
      if (dataset === this.plot.dataset) this.loadInstanceOptions(true);
      this.plot.dataset = dataset;
    },
    "plot.dataset"() {
      this.plot.field = this.defaultField();
      this.plot.splitBy = null;
      this.loadInstanceOptions(true);
    },
    "plot.splitBy"() {
      this.plot.splitValues = [];
      this.splitFilter = "";
      this.loadSplitOptions();
    },
    view: { handler() { this.applyView(); this.scheduleFetch(false); }, deep: true },
    events() {
      // Markers are drawn by the chart, which only needs a redraw.
      this.chart?.redraw(false, false);
    },
    themeVersion() {
      // Charts take their colors at creation, so they are rebuilt from the last response.
      if (!this.lastRes) return;
      this.rebuildPending = true;
      if (this.lastRes.edges) this.renderHistogram(this.lastRes);
      else this.render(this.lastRes);
    },
  },
  created() {
    // Not reactive: chart state is owned by uPlot.
    this.chart = null;
    this.records = [];
    this.focusedSeries = -1;
    this.lastRes = null;
    this.hovering = false;
    this.fetchTimer = null;
    this.abort = null;
    // Any change of the query inputs refetches and rebuilds the chart.
    this.$watch(
      () => [this.plot.source, this.plot.dataset, this.plot.field, this.plot.splitBy, [...this.plot.splitValues], this.plot.filter, this.plot.instance, this.plot.mode, this.shift, this.timeMode],
      () => this.scheduleFetch(true),
    );
  },
  mounted() {
    this.resizeObserver = new ResizeObserver(() => {
      if (this.chart) this.chart.setSize({ width: this.$refs.chart.clientWidth, height: CHART_HEIGHT });
    });
    this.resizeObserver.observe(this.$refs.chart);
    if (!this.plot.dataset) this.plot.dataset = this.defaultDataset();
    if (!this.plot.field) this.plot.field = this.defaultField();
    this.loadInstanceOptions(this.plot.instance == null);
    this.scheduleFetch(true);
  },
  beforeUnmount() {
    this.resizeObserver.disconnect();
    clearTimeout(this.fetchTimer);
    this.abort?.abort();
    this.chart?.destroy();
  },
  methods: {
    /** DEFAULT_DATASET if the source has it, else its first dataset. */
    defaultDataset() {
      return (this.datasets.find((d) => d.name === DEFAULT_DATASET) ?? this.datasets[0])?.name ?? null;
    },

    /** DEFAULT_FIELD if the dataset has it, else its first numeric field. */
    defaultField() {
      return (this.numericFields.find((f) => f.name === DEFAULT_FIELD) ?? this.numericFields[0])?.name ?? null;
    },

    async loadSplitOptions() {
      this.splitOptions = [];
      if (!this.plot.splitBy) return;
      try {
        this.splitOptions = await getJSON("/api/context", { source: this.plot.source, dataset: this.plot.dataset, field: this.plot.splitBy });
      } catch (e) {
        this.error = e.message;
      }
    },

    /** @param {boolean} selectFirst Whether to select the first instance, e.g. after a dataset change. */
    async loadInstanceOptions(selectFirst) {
      this.instanceOptions = [];
      if (!this.dataset?.instance) {
        this.plot.instance = null;
        return;
      }
      const dataset = this.plot.dataset;
      try {
        const values = await getJSON("/api/context", { source: this.plot.source, dataset, field: this.dataset.instance });
        // The dataset may have changed while the request was in flight.
        if (dataset !== this.plot.dataset) return;
        this.instanceOptions = values.map(String);
        if (selectFirst) this.plot.instance = this.instanceOptions[0] ?? null;
      } catch (e) {
        this.error = e.message;
      }
    },

    applyFilter() {
      this.plot.filter = this.filterDraft.trim();
    },

    toggleSplit(value) {
      const key = String(value);
      const idx = this.plot.splitValues.indexOf(key);
      if (idx >= 0) this.plot.splitValues.splice(idx, 1);
      else this.plot.splitValues.push(key);
    },

    /** @param {boolean} rebuild Whether the series set may have changed. */
    scheduleFetch(rebuild) {
      this.rebuildPending = this.rebuildPending || rebuild;
      clearTimeout(this.fetchTimer);
      this.fetchTimer = setTimeout(() => this.fetch(), FETCH_DELAY_MS);
    },

    async fetch() {
      if (!this.plot.dataset || !this.plot.field) return;
      this.abort?.abort();
      this.abort = new AbortController();
      const width = Math.max(100, Math.round(this.$refs.chart.clientWidth));
      const params = {
        source: this.plot.source,
        dataset: this.plot.dataset,
        field: this.plot.field,
        split_by: this.plot.splitBy,
        split_values: this.plot.splitValues.length ? this.plot.splitValues : null,
        filter: this.plot.filter || null,
        instance: this.dataset?.instance ? this.plot.instance : null,
      };
      if (this.view) {
        params.t0 = this.view.min - this.shift;
        params.t1 = this.view.max - this.shift;
      }
      this.loading = true;
      try {
        const signal = this.abort.signal;
        const histogram = this.plot.mode === "histogram";
        const [res, stats] = await Promise.all([
          histogram ? getJSON("/api/histogram", params, signal) : getJSON("/api/series", { ...params, width }, signal),
          getJSON("/api/stats", params, signal),
        ]);
        this.error = "";
        if (histogram) this.renderHistogram(res);
        else this.render(res);
        this.stats = stats.series;
        this.statsSampled = stats.sampled;
      } catch (e) {
        if (e.name !== "AbortError") this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    render(res) {
      this.lastRes = res;
      this.downsampled = res.downsampled;
      this.totalSplits = res.total_splits;
      this.nofSeries = res.series.length;
      const shift = this.shift;
      const tables = res.series.map((s) => [s.t.map((t) => t + shift), s.v, s.record]);
      // Series have their own timestamps, so they are aligned on the union of them.
      const joined = tables.length ? uPlot.join(tables) : [[]];
      const values = [];
      this.records = [];
      for (let i = 0; i < tables.length; i++) {
        values.push(joined[1 + 2 * i]);
        this.records.push(joined[2 + 2 * i]);
      }

      let maxAbs = 0;
      for (const s of res.series) for (const v of s.v) maxAbs = Math.max(maxAbs, Math.abs(v));
      const unit = displayUnit(res.unit, maxAbs);
      const scaled = values.map((col) => col.map((v) => (v == null ? v : v / unit.divisor)));
      const data = [joined[0], ...scaled];
      const labels = res.series.map((s) => s.label);
      this.unit = unit;
      this.labels = labels;

      const key = JSON.stringify(["time", labels, unit.label]);
      if (this.chart && !this.rebuildPending && this.chartKey === key) {
        this.chart.setData(data, false);
      } else {
        this.chart?.destroy();
        this.chartKey = key;
        this.chart = this.createChart(data, labels, unit.label);
      }
      this.rebuildPending = false;
      this.applyView();
    },

    renderHistogram(res) {
      this.lastRes = res;
      this.downsampled = false;
      this.totalSplits = res.total_splits;
      this.nofSeries = res.series.length;
      this.records = [];
      let maxAbs = 0;
      for (const e of res.edges) maxAbs = Math.max(maxAbs, Math.abs(e));
      const unit = displayUnit(res.unit, maxAbs);
      const labels = res.series.map((s) => s.label);
      this.unit = unit;
      this.labels = labels;
      // A stepped path draws bin i from edge i to edge i+1, so the last count is repeated at the last edge.
      const data = [
        res.edges.map((e) => e / unit.divisor),
        ...res.series.map((s) => [...s.counts, s.counts[s.counts.length - 1]]),
      ];

      const key = JSON.stringify(["histogram", labels, unit.label]);
      if (this.chart && !this.rebuildPending && this.chartKey === key) {
        this.chart.setData(data);
      } else {
        this.chart?.destroy();
        this.chartKey = key;
        this.chart = this.createHistogramChart(data, labels, unit.label);
      }
      this.rebuildPending = false;
    },

    /** Shows the time and value under the mouse, or only the time when the cursor is synced from another plot. */
    updateCursorReadout(u) {
      const { left, top } = u.cursor;
      if (left == null || left < 0) {
        this.cursorText = "";
        this.cursorEvent = null;
        return;
      }
      this.cursorEvent = this.hovering && this.plot.mode !== "histogram" ? this.eventAt(u, left) : null;
      const histogram = this.plot.mode === "histogram";
      const unit = this.unit.label ? ` ${this.unit.label}` : "";
      const x = u.posToVal(left, "x");
      let text = histogram ? `${formatStat(x)}${unit}` : formatTime(x, this.timeMode);
      if (this.hovering && top != null && top >= 0) {
        const y = u.posToVal(top, "y");
        text += histogram ? ` \u00b7 count ${formatStat(Math.max(0, y))}` : ` \u00b7 ${formatStat(y)}${unit}`;
      }
      this.cursorText = text;
    },

    /** Tracks whether the mouse is over this chart, as opposed to a cursor synced from another plot. */
    trackHover(chart) {
      chart.over.addEventListener("mouseenter", () => { this.hovering = true; });
      chart.over.addEventListener("mouseleave", () => {
        this.hovering = false;
        this.cursorText = "";
      });
    },

    applyView() {
      if (this.chart && this.view && this.plot.mode !== "histogram") {
        this.chart.setScale("x", { min: this.view.min, max: this.view.max });
      }
    },

    createHistogramChart(data, labels, unitLabel) {
      const axisColor = cssVar("--fg-muted");
      const gridColor = cssVar("--grid");
      const axis = { stroke: axisColor, grid: { stroke: gridColor, width: 1 }, ticks: { stroke: gridColor, width: 1 } };
      const single = labels.length === 1;
      const opts = {
        width: this.$refs.chart.clientWidth,
        height: CHART_HEIGHT,
        scales: { x: { time: false } },
        series: [
          { label: unitLabel ? `value [${unitLabel}]` : "value", value: (u, v) => (v == null ? "--" : formatStat(v)) },
          ...labels.map((label, i) => {
            const color = seriesColor(i);
            return { label, stroke: color, width: 1.5, paths: steppedPath, points: { show: false }, fill: single ? color + "40" : undefined };
          }),
        ],
        axes: [{ ...axis, label: unitLabel }, { ...axis, label: "count", size: 60 }],
        cursor: { drag: { x: false, y: false }, focus: { prox: 16 } },
        focus: { alpha: 0.35 },
        hooks: { setCursor: [(u) => this.updateCursorReadout(u)] },
      };
      const chart = new uPlot(opts, data, this.$refs.chart);
      this.trackHover(chart);
      return chart;
    },

    createChart(data, labels, unitLabel) {
      const axisColor = cssVar("--fg-muted");
      const gridColor = cssVar("--grid");
      const axis = { stroke: axisColor, grid: { stroke: gridColor, width: 1 }, ticks: { stroke: gridColor, width: 1 } };
      const absolute = this.timeMode === "absolute";
      const xAxis = absolute ? { ...axis, values: timeTicks, space: TIME_TICK_SPACE } : { ...axis };
      const opts = {
        width: this.$refs.chart.clientWidth,
        height: CHART_HEIGHT,
        scales: { x: { time: absolute } },
        tzDate: utcDate,
        series: [
          absolute
            ? { label: "time (UTC)", value: (u, ts) => (ts == null ? "--" : fmtFull(utcDate(ts))) }
            : { label: "time (s)", value: (u, t) => (t == null ? "--" : t.toFixed(3)) },
          ...labels.map((label, i) => ({ label, stroke: seriesColor(i), width: 1.25, spanGaps: true })),
        ],
        axes: [xAxis, { ...axis, label: unitLabel, size: 60 }],
        cursor: { drag: { x: true, y: false, setScale: false }, sync: { key: CURSOR_SYNC_KEY }, focus: { prox: 16 } },
        focus: { alpha: 0.35 },
        hooks: {
          setSelect: [selectToZoom((range) => this.$emit("zoom", range))],
          setSeries: [(u, idx) => { this.focusedSeries = idx ?? -1; }],
          setCursor: [(u) => this.updateCursorReadout(u)],
          draw: [(u) => this.drawEvents(u)],
        },
      };
      const chart = new uPlot(opts, data, this.$refs.chart);
      this.trackHover(chart);
      attachZoomPan(chart, (range) => this.$emit("zoom", range), () => this.drillDown(chart));
      return chart;
    },

    /**
     * Event whose marker is nearest to a cursor position, within EVENT_HIT_PX, or null.
     * @param {any} u
     * @param {number} left Cursor position in CSS pixels from the left of the plot area.
     */
    eventAt(u, left) {
      let best = null;
      let bestDist = EVENT_HIT_PX;
      for (const ev of this.events) {
        const d = Math.abs(u.valToPos(ev.t, "x") - left);
        if (d <= bestDist) {
          best = ev;
          bestDist = d;
        }
      }
      return best;
    },

    /** Draws the event markers as dashed vertical lines over the plot area, colored by category. */
    drawEvents(u) {
      if (!this.events.length) return;
      const { ctx, bbox } = u;
      const colors = {};
      ctx.save();
      ctx.lineWidth = Math.max(1, devicePixelRatio);
      ctx.globalAlpha = 0.75;
      const dash = 4 * devicePixelRatio;
      for (const ev of this.events) {
        const x = Math.round(u.valToPos(ev.t, "x", true));
        if (x < bbox.left || x > bbox.left + bbox.width) continue;
        ctx.strokeStyle = colors[ev.category] ??= cssVar(`--ev-${ev.category}`);
        ctx.setLineDash([dash, dash]);
        ctx.beginPath();
        ctx.moveTo(x, bbox.top);
        ctx.lineTo(x, bbox.top + bbox.height);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = ctx.strokeStyle;
        ctx.fillRect(x - 2 * devicePixelRatio, bbox.top, 4 * devicePixelRatio, 4 * devicePixelRatio);
      }
      ctx.restore();
    },

    drillDown(chart) {
      // An event marker under the cursor takes precedence over the data points.
      const ev = chart.cursor.left >= 0 ? this.eventAt(chart, chart.cursor.left) : null;
      if (ev) {
        this.$emit("select-record", { source: ev.source ?? this.plot.source, record: ev.record });
        return;
      }
      const idx = chart.cursor.idx;
      if (idx == null || !this.records.length) return;
      let si = this.focusedSeries > 0 ? this.focusedSeries - 1 : this.records.findIndex((r) => r[idx] != null);
      if (si < 0) si = 0;
      const j = nearestDefined(this.records[si], idx);
      if (j >= 0) this.$emit("select-record", { source: this.plot.source, record: this.records[si][j], field: this.plot.field });
    },
  },
  template: `
    <section class="panel">
      <header class="panel-bar">
        <select v-if="showSource" v-model.number="plot.source" :title="source ? source.path : 'Source'">
          <option v-for="s in choices ?? sources" :key="s.id" :value="s.id" :disabled="s.status !== 'ready'">
            {{ s.file ?? s.name }}{{ s.status === "parsing" ? " (parsing)" : s.status === "error" ? " (error)" : "" }}
          </option>
        </select>
        <select v-model="plot.dataset" title="Dataset">
          <option v-for="d in datasets" :key="d.name" :value="d.name">{{ d.label }}</option>
        </select>
        <select v-if="dataset && dataset.instance" v-model="plot.instance" :title="dataset.instance">
          <option :value="null">all</option>
          <option v-for="v in instanceOptions" :key="v" :value="v">{{ v }}</option>
        </select>
        <select v-model="plot.field" title="Field" class="field-select">
          <option v-for="f in numericFields" :key="f.name" :value="f.name">{{ f.name }}</option>
        </select>
        <select v-model="plot.mode" title="View">
          <option value="time">time series</option>
          <option value="histogram">histogram</option>
        </select>
        <label class="inline">split by
          <select v-model="plot.splitBy">
            <option :value="null">none</option>
            <option v-for="g in splitFields" :key="g" :value="g">{{ g }}</option>
          </select>
        </label>
        <details v-if="plot.splitBy" class="splits">
          <summary>{{ splitSummary }}</summary>
          <div class="splits-popup">
            <input v-model="splitFilter" placeholder="filter" />
            <button v-if="plot.splitValues.length" @click="plot.splitValues.splice(0)">clear</button>
            <label v-for="v in listedSplits" :key="v" class="split-option">
              <input type="checkbox" :checked="plot.splitValues.includes(String(v))" @change="toggleSplit(v)" /> {{ v }}
            </label>
            <div v-if="splitOptions.length > listedSplits.length" class="muted">filter to see more</div>
          </div>
        </details>
        <form class="filter" @submit.prevent="applyFilter">
          <input v-model="filterDraft" :class="{ dirty: filterDirty }" placeholder="rnti > 0x4605 and pci == 1"
                 title="Comparisons (== != < <= > >=, is null) joined by and/or/not. Values in base units (us, bps)." @blur="applyFilter" />
        </form>
        <span class="status">
          <span v-if="loading" class="muted">loading</span>
          <span v-else-if="plot.mode === 'histogram'" class="muted">distribution of the visible window</span>
          <span v-else-if="downsampled" class="muted" title="min/max per pixel; zoom in for full resolution">downsampled</span>
          <span v-if="error" class="error">{{ error }}</span>
        </span>
        <button class="icon" title="Remove plot" @click="$emit('remove')">✕</button>
      </header>
      <div class="chart-wrap">
        <div ref="chart" class="chart"></div>
        <div v-if="cursorText" class="cursor-readout">
          {{ cursorText }}
          <div v-if="cursorEvent" :class="['cursor-event', 'ev-' + cursorEvent.category]">
            <span class="event-dot"></span>{{ cursorEvent.type }}: {{ cursorEvent.text }}
          </div>
        </div>
      </div>
      <details v-if="statsRows.length" class="stats" open>
        <summary class="muted">statistics of the visible window{{ unit.label ? " [" + unit.label + "]" : "" }}{{ statsSampled ? ", percentiles sampled" : "" }}</summary>
        <table>
          <thead><tr><th></th><th>count</th><th>min</th><th>mean</th><th>p50</th><th>p95</th><th>p99</th><th>max</th></tr></thead>
          <tbody>
            <tr v-for="r in statsRows" :key="r.label">
              <td><span class="swatch" :style="{ background: r.color }"></span>{{ r.label }}</td>
              <td>{{ r.count }}</td><td>{{ r.min }}</td><td>{{ r.mean }}</td><td>{{ r.p50 }}</td><td>{{ r.p95 }}</td><td>{{ r.p99 }}</td><td>{{ r.max }}</td>
            </tr>
          </tbody>
        </table>
      </details>
    </section>
  `,
};
