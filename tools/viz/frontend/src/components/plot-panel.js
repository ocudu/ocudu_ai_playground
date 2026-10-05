// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import uPlot from "uplot";
import { getJSON } from "../api.js";
import { displayUnit } from "../units.js";

const PALETTE = [
  "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
  "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
];
const CHART_HEIGHT = 260;
// Delay before fetching after the view changes, to coalesce wheel and pan events.
const FETCH_DELAY_MS = 120;
// Group values listed in the group picker.
const MAX_LISTED_GROUPS = 300;

const fmtMs = uPlot.fmtDate("{HH}:{mm}:{ss}.{fff}");
const fmtSec = uPlot.fmtDate("{HH}:{mm}:{ss}");
const fmtMin = uPlot.fmtDate("{HH}:{mm}");
const fmtFull = uPlot.fmtDate("{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}.{fff}");

/** @param {number} ts */
function utcDate(ts) {
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
function timeTicks(u, splits, axisIdx, space, incr) {
  const fmt = incr < 1 ? fmtMs : incr < 60 ? fmtSec : fmtMin;
  return splits.map((ts) => fmt(utcDate(ts)));
}

/**
 * Formats a stats value for a table cell.
 * @param {number | null} v
 */
function formatStat(v) {
  if (v == null) return "\u2013";
  if (v !== 0 && (Math.abs(v) >= 1e6 || Math.abs(v) < 1e-3)) return v.toExponential(3);
  return String(Number(v.toPrecision(5)));
}

/** @param {string} name */
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
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
  },
  emits: ["zoom", "remove", "select-record"],
  data() {
    return {
      loading: false,
      error: "",
      downsampled: false,
      totalGroups: 0,
      nofSeries: 0,
      groupValues: [],
      groupFilter: "",
      filterDraft: this.plot.filter,
      stats: [],
      statsSampled: false,
      unit: { divisor: 1, label: "" },
      labels: [],
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
    groupFields() {
      return this.dataset ? this.dataset.context : [];
    },
    shift() {
      return this.shifts[this.plot.source] || 0;
    },
    listedGroups() {
      const filter = this.groupFilter.trim();
      const values = filter ? this.groupValues.filter((v) => String(v).includes(filter)) : this.groupValues;
      return values.slice(0, MAX_LISTED_GROUPS);
    },
    statsRows() {
      return this.stats.map((s) => {
        const idx = this.labels.indexOf(s.label);
        const color = idx >= 0 ? PALETTE[idx % PALETTE.length] : "transparent";
        const scale = (v) => formatStat(v == null ? v : v / this.unit.divisor);
        return { label: s.label, color, count: s.count.toLocaleString(), min: scale(s.min), mean: scale(s.mean), p50: scale(s.p50), p95: scale(s.p95), p99: scale(s.p99), max: scale(s.max) };
      });
    },
    filterDirty() {
      return this.filterDraft.trim() !== this.plot.filter;
    },
    groupSummary() {
      if (this.plot.groups.length) return `${this.plot.groups.length} selected`;
      if (this.totalGroups > this.nofSeries) return `first ${this.nofSeries} of ${this.totalGroups}`;
      return "all";
    },
  },
  watch: {
    "plot.source"() {
      this.plot.dataset = this.datasets[0]?.name ?? null;
    },
    "plot.dataset"() {
      this.plot.field = this.numericFields[0]?.name ?? null;
      this.plot.groupBy = null;
    },
    "plot.groupBy"() {
      this.plot.groups = [];
      this.groupFilter = "";
      this.loadGroupValues();
    },
    view:{ handler() { this.applyView(); this.scheduleFetch(false); }, deep: true },
  },
  created() {
    // Not reactive: chart state is owned by uPlot.
    this.chart = null;
    this.records = [];
    this.focusedSeries = -1;
    this.fetchTimer = null;
    this.abort = null;
    // Any change of the query inputs refetches and rebuilds the chart.
    this.$watch(
      () => [this.plot.source, this.plot.dataset, this.plot.field, this.plot.groupBy, [...this.plot.groups], this.plot.filter, this.shift, this.timeMode],
      () => this.scheduleFetch(true),
    );
  },
  mounted() {
    this.resizeObserver = new ResizeObserver(() => {
      if (this.chart) this.chart.setSize({ width: this.$refs.chart.clientWidth, height: CHART_HEIGHT });
    });
    this.resizeObserver.observe(this.$refs.chart);
    if (!this.plot.dataset) this.plot.dataset = this.datasets[0]?.name ?? null;
    if (!this.plot.field) this.plot.field = this.numericFields[0]?.name ?? null;
    this.scheduleFetch(true);
  },
  beforeUnmount() {
    this.resizeObserver.disconnect();
    clearTimeout(this.fetchTimer);
    this.abort?.abort();
    this.chart?.destroy();
  },
  methods: {
    async loadGroupValues() {
      this.groupValues = [];
      if (!this.plot.groupBy) return;
      try {
        this.groupValues = await getJSON("/api/context", { source: this.plot.source, dataset: this.plot.dataset, field: this.plot.groupBy });
      } catch (e) {
        this.error = e.message;
      }
    },

    applyFilter() {
      this.plot.filter = this.filterDraft.trim();
    },

    toggleGroup(value) {
      const key = String(value);
      const idx = this.plot.groups.indexOf(key);
      if (idx >= 0) this.plot.groups.splice(idx, 1);
      else this.plot.groups.push(key);
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
        group_by: this.plot.groupBy,
        groups: this.plot.groups.length ? this.plot.groups : null,
        filter: this.plot.filter || null,
      };
      if (this.view) {
        params.t0 = this.view.min - this.shift;
        params.t1 = this.view.max - this.shift;
      }
      this.loading = true;
      try {
        const signal = this.abort.signal;
        const [res, stats] = await Promise.all([
          getJSON("/api/series", { ...params, width }, signal),
          getJSON("/api/stats", params, signal),
        ]);
        this.error = "";
        this.render(res);
        this.stats = stats.series;
        this.statsSampled = stats.sampled;
      } catch (e) {
        if (e.name !== "AbortError") this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    render(res) {
      this.downsampled = res.downsampled;
      this.totalGroups = res.total_groups;
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

      const sameSeries = this.chart && !this.rebuildPending && this.chartKey === JSON.stringify([labels, unit.label]);
      if (sameSeries) {
        this.chart.setData(data, false);
      } else {
        this.chart?.destroy();
        this.chartKey = JSON.stringify([labels, unit.label]);
        this.chart = this.createChart(data, labels, unit.label);
      }
      this.rebuildPending = false;
      this.applyView();
    },

    applyView() {
      if (this.chart && this.view) this.chart.setScale("x", { min: this.view.min, max: this.view.max });
    },

    createChart(data, labels, unitLabel) {
      const axisColor = cssVar("--fg-muted");
      const gridColor = cssVar("--grid");
      const axis = { stroke: axisColor, grid: { stroke: gridColor, width: 1 }, ticks: { stroke: gridColor, width: 1 } };
      const absolute = this.timeMode === "absolute";
      // Minimum pixels between time ticks, so that HH:mm:ss.fff labels do not overlap.
      const xAxis = absolute ? { ...axis, values: timeTicks, space: 110 } : { ...axis };
      const opts = {
        width: this.$refs.chart.clientWidth,
        height: CHART_HEIGHT,
        scales: { x: { time: absolute } },
        tzDate: utcDate,
        series: [
          absolute
            ? { label: "time (UTC)", value: (u, ts) => (ts == null ? "--" : fmtFull(utcDate(ts))) }
            : { label: "time (s)", value: (u, t) => (t == null ? "--" : t.toFixed(3)) },
          ...labels.map((label, i) => ({ label, stroke: PALETTE[i % PALETTE.length], width: 1.25, spanGaps: true })),
        ],
        axes: [xAxis, { ...axis, label: unitLabel, size: 60 }],
        cursor: { drag: { x: true, y: false, setScale: false }, sync: { key: "ocudu-viz" }, focus: { prox: 16 } },
        focus: { alpha: 0.35 },
        hooks: {
          setSelect: [
            (u) => {
              if (u.select.width > 2) {
                this.$emit("zoom", { min: u.posToVal(u.select.left, "x"), max: u.posToVal(u.select.left + u.select.width, "x") });
              }
              u.setSelect({ left: 0, top: 0, width: 0, height: 0 }, false);
            },
          ],
          setSeries: [(u, idx) => { this.focusedSeries = idx ?? -1; }],
        },
      };
      const chart = new uPlot(opts, data, this.$refs.chart);
      this.attachInteractions(chart);
      return chart;
    },

    attachInteractions(chart) {
      const over = chart.over;
      const xRange = () => ({ min: chart.scales.x.min, max: chart.scales.x.max });

      over.addEventListener("wheel", (e) => {
        e.preventDefault();
        const { min, max } = xRange();
        const at = chart.posToVal(e.offsetX, "x");
        const factor = e.deltaY < 0 ? 0.8 : 1.25;
        this.$emit("zoom", { min: at - (at - min) * factor, max: at + (max - at) * factor });
      }, { passive: false });

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
          this.$emit("zoom", { min: start.min - dv, max: start.max - dv });
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
        // Clicks ending a drag-to-zoom are not drill-downs.
        if (downX === null || Math.abs(e.clientX - downX) > 3) return;
        this.drillDown(chart);
      });
      over.addEventListener("dblclick", () => this.$emit("zoom", null));
    },

    drillDown(chart) {
      const idx = chart.cursor.idx;
      if (idx == null || !this.records.length) return;
      let si = this.focusedSeries > 0 ? this.focusedSeries - 1 : this.records.findIndex((r) => r[idx] != null);
      if (si < 0) si = 0;
      const j = nearestDefined(this.records[si], idx);
      if (j >= 0) this.$emit("select-record", { source: this.plot.source, record: this.records[si][j] });
    },
  },
  template: `
    <section class="panel">
      <header class="panel-bar">
        <select v-model.number="plot.source" :title="source ? source.path : 'Source'">
          <option v-for="s in sources" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <select v-model="plot.dataset" title="Dataset">
          <option v-for="d in datasets" :key="d.name" :value="d.name">{{ d.name }}</option>
        </select>
        <select v-model="plot.field" title="Field" class="field-select">
          <option v-for="f in numericFields" :key="f.name" :value="f.name">{{ f.name }}{{ f.unit ? " [" + f.unit + "]" : "" }}</option>
        </select>
        <label class="inline">group by
          <select v-model="plot.groupBy">
            <option :value="null">none</option>
            <option v-for="g in groupFields" :key="g" :value="g">{{ g }}</option>
          </select>
        </label>
        <details v-if="plot.groupBy" class="groups">
          <summary>{{ groupSummary }}</summary>
          <div class="groups-popup">
            <input v-model="groupFilter" placeholder="filter" />
            <button v-if="plot.groups.length" @click="plot.groups.splice(0)">clear</button>
            <label v-for="v in listedGroups" :key="v" class="group-option">
              <input type="checkbox" :checked="plot.groups.includes(String(v))" @change="toggleGroup(v)" /> {{ v }}
            </label>
            <div v-if="groupValues.length > listedGroups.length" class="muted">filter to see more</div>
          </div>
        </details>
        <form class="filter" @submit.prevent="applyFilter">
          <input v-model="filterDraft" :class="{ dirty: filterDirty }" placeholder="rnti > 0x4605 and pci == 1"
                 title="Comparisons (== != < <= > >=, is null) joined by and/or/not. Values in base units (us, bps)." @blur="applyFilter" />
        </form>
        <span class="status">
          <span v-if="loading" class="muted">loading</span>
          <span v-else-if="downsampled" class="muted" title="min/max per pixel; zoom in for full resolution">downsampled</span>
          <span v-if="error" class="error">{{ error }}</span>
        </span>
        <button class="icon" title="Remove plot" @click="$emit('remove')">✕</button>
      </header>
      <div ref="chart" class="chart"></div>
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
