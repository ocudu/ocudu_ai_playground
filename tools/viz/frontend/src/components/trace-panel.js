// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import uPlot from "uplot";
import { getJSON } from "../api.js";
import { CURSOR_SYNC_KEY, TIME_TICK_SPACE, attachZoomPan, cssVar, formatTime, selectToZoom, timeTicks, utcDate } from "./chart-utils.js";

// Height of a row of the trace in CSS pixels, and of the space taken by the time axis.
const ROW_HEIGHT = 18;
const AXIS_HEIGHT = 68;
// Rows of height the chart has at least, so that a trace of one or two rows does not squash them under the axis.
const MIN_CHART_ROWS = 3;
// UE rows shown at once. More UEs are reached with the scrollbar of the trace.
const VISIBLE_UE_ROWS = 25;
// UEs requested for a window.
const MAX_LANES = 2000;
// Width of the row label axis, the same as the value axis of the plots with its label, so that times line up. Full
// lane labels show when hovering a row.
const LABEL_AXIS_SIZE = 90;
// Position of the bars in their row, from its top.
const BAR_POSITION = 0.6;
// Distance in CSS pixels within which the cursor is on an event.
const EVENT_HIT_PX = 5;
const FETCH_DELAY_MS = 120;
// Glyph of each event category, also shown in the legend.
const GLYPHS = { ra: "▲", lifecycle: "■", rrc: "●", f1ap: "●", ngap: "●", e1ap: "●", mobility: "◆", failure: "✖", warning: "●", error: "●" };
// Identifiers of the UE contexts of pcaps, by the event category of their protocol, that rows can be grouped by.
const PROTOCOL_IDS = { f1ap: ["du_f1ap", "cu_f1ap"], ngap: ["ran_ngap", "amf_ngap"], e1ap: ["cu_cp_e1ap", "cu_up_e1ap"] };
// Categories of the legend, in order, shown when the source has events of them.
const LEGEND = [
  ["ra", "random access"],
  ["lifecycle", "UE lifecycle"],
  ["rrc", "RRC"],
  ["f1ap", "F1AP"],
  ["ngap", "NGAP"],
  ["e1ap", "E1AP"],
  ["mobility", "mobility"],
  ["failure", "failures"],
];

/**
 * Draws the glyph of a category centred on (x, y).
 * @param {CanvasRenderingContext2D} ctx
 * @param {string} category
 * @param {number} x
 * @param {number} y
 * @param {number} r Half size in canvas pixels.
 */
function drawGlyph(ctx, category, x, y, r) {
  ctx.beginPath();
  if (category === "ra") {
    ctx.moveTo(x, y - r);
    ctx.lineTo(x + r, y + r);
    ctx.lineTo(x - r, y + r);
  } else if (category === "lifecycle") {
    ctx.rect(x - r, y - r, 2 * r, 2 * r);
  } else if (category === "mobility") {
    ctx.moveTo(x, y - r);
    ctx.lineTo(x + r, y);
    ctx.lineTo(x, y + r);
    ctx.lineTo(x - r, y);
  } else if (category === "failure") {
    ctx.moveTo(x - r, y - r);
    ctx.lineTo(x + r, y + r);
    ctx.moveTo(x + r, y - r);
    ctx.lineTo(x - r, y + r);
    ctx.stroke();
    return;
  } else {
    ctx.arc(x, y, r, 0, 2 * Math.PI);
  }
  ctx.closePath();
  ctx.fill();
}

/**
 * All the UE identifiers of a row, shown when hovering it: the one it is grouped by first, then the others, with the
 * values of all its UE contexts, e.g. "rnti=0x4602 ue=1 du_f1ap=1 cu_f1ap=1".
 * @param {{ids?: Record<string, string[]>, ue: number | null, rnti: string | null, label: string | null}} lane
 * @param {string} by
 */
function laneLabel(lane, by) {
  if (lane.ids && Object.keys(lane.ids).length) {
    const rank = (name) => (name === by ? 0 : name === "rnti" ? 1 : name === "ue" ? 2 : 3);
    const names = Object.keys(lane.ids).sort((a, b) => rank(a) - rank(b));
    return names.map((name) => `${name}=${lane.ids[name].join(",")}`).join(" ");
  }
  const ids = [lane.ue != null ? `ue=${lane.ue}` : null, lane.rnti ? `rnti=${lane.rnti}` : null, lane.label];
  return ids.filter(Boolean).join(" ") || "UE";
}

/**
 * Label of a row on the row axis: the identifier the rows are grouped by and its value, e.g. "rnti=0x4601", as the
 * server labels the rows of a value, or "–" for a row of a UE context without it.
 * @param {{label: string | null}} lane
 * @param {string} by
 */
function axisLabel(lane, by) {
  return lane.label?.startsWith(`${by}=`) ? lane.label : "–";
}

export default {
  name: "TracePanel",
  props: {
    panel: { type: Object, required: true },
    sources: { type: Array, required: true },
    view: { type: Object, default: null },
    shifts: { type: Array, required: true },
    timeMode: { type: String, required: true },
    themeVersion: { type: Number, default: 0 },
    // Sources the panel may show, e.g. the sources of its tab, or all sources when null.
    choices: { type: Array, default: null },
    // Run of the tab, whose logs can be joined to an F1AP pcap.
    runId: { type: Number, default: null },
  },
  emits: ["zoom", "remove", "select-record"],
  data() {
    return {
      loading: false,
      error: "",
      nofLanes: 0,
      totalLanes: 0,
      truncated: false,
      // Height of the chart and of the content it scrolls over, in CSS pixels.
      chartHeight: AXIS_HEIGHT + ROW_HEIGHT,
      scrollHeight: AXIS_HEIGHT + ROW_HEIGHT,
      cursorText: "",
      // Event or UE under the mouse, shown with the cursor readout.
      cursorEvent: null,
      cursorLane: "",
      filterDraft: this.panel.filter ?? "",
    };
  },
  computed: {
    source() {
      return this.sources[this.panel.source];
    },
    shift() {
      return this.shifts[this.panel.source] || 0;
    },
    eventsStatus() {
      return this.source?.events_status;
    },
    notes() {
      return this.source?.notes ?? [];
    },
    filterDirty() {
      return this.filterDraft.trim() !== (this.panel.filter ?? "");
    },
    /** Identifier the rows are grouped by: the chosen one when the source has it, else the RNTI. */
    groupBy() {
      return this.groupOptions.includes(this.panel.groupBy) ? this.panel.groupBy : "rnti";
    },
    /** Identifiers that rows can be grouped by: the RNTI, the default, the DU UE index of logs, and the UE identifiers of a pcap. */
    groupOptions() {
      const counts = this.source?.event_counts ?? {};
      const isPcap = this.source?.type === "pcap";
      const protocolIds = isPcap ? Object.keys(PROTOCOL_IDS).filter((p) => counts[p]).flatMap((p) => PROTOCOL_IDS[p]) : [];
      return ["rnti", ...(!isPcap || this.joined ? ["ue"] : []), ...protocolIds];
    },
    /** F1AP pcap of the tab, whose UE contexts identify the UEs of its logs. */
    f1apSource() {
      if (this.runId == null) return null;
      return (this.choices ?? []).find((s) => s.type === "pcap" && s.status === "ready" && s.event_counts?.f1ap) ?? null;
    },
    /** Logs of the tab with events, which join the UE contexts of the F1AP pcap. */
    joinableLogs() {
      if (!this.f1apSource) return [];
      return (this.choices ?? []).filter((s) => s.type !== "pcap" && s.status === "ready" && Object.keys(s.event_counts ?? {}).length);
    },
    /** Whether a trace of the F1AP pcap also shows the UE events of the logs of the tab. */
    joined() {
      return this.source === this.f1apSource && this.joinableLogs.length > 0 && this.panel.joined === true;
    },
    /** Whether a trace of a log shows its UE events on the UE contexts of the F1AP pcap, rather than its own. */
    logOnF1ap() {
      return this.joinableLogs.includes(this.source);
    },
    legend() {
      const counts = { ...(this.source?.event_counts ?? {}) };
      if (this.joined) {
        for (const s of this.joinableLogs) Object.assign(counts, s.event_counts);
      }
      return LEGEND.filter(([category]) => counts[category]).map(([category, label]) => ({ category, label, glyph: GLYPHS[category] }));
    },
    scrollable() {
      return this.nofLanes > VISIBLE_UE_ROWS;
    },
  },
  watch: {
    view: { handler() { this.scheduleFetch(); }, deep: true },
    eventsStatus() {
      this.scheduleFetch();
    },
    shift() {
      this.scheduleFetch();
    },
    "panel.source"() {
      this.scheduleFetch();
    },
    "panel.filter"() {
      this.scheduleFetch();
    },
    "panel.groupBy"() {
      this.scheduleFetch();
    },
    joined() {
      this.scheduleFetch();
    },
    logOnF1ap() {
      this.scheduleFetch();
    },
    timeMode() {
      this.rebuild();
    },
    themeVersion() {
      this.rebuild();
    },
  },
  created() {
    // Not reactive: drawing state owned by the chart.
    this.chart = null;
    this.lanes = [];
    this.events = [];
    this.hasCellRow = false;
    // First UE row shown, set by the scrollbar.
    this.firstRow = 0;
    this.hovering = false;
    this.fetchTimer = null;
    this.abort = null;
  },
  mounted() {
    this.resizeObserver = new ResizeObserver(() => {
      if (this.chart) this.chart.setSize({ width: this.chartWidth(), height: this.chartHeight });
    });
    this.resizeObserver.observe(this.$refs.scroller);
    this.scheduleFetch();
  },
  beforeUnmount() {
    this.resizeObserver.disconnect();
    clearTimeout(this.fetchTimer);
    this.abort?.abort();
    this.chart?.destroy();
  },
  methods: {
    applyFilter() {
      this.panel.filter = this.filterDraft.trim();
    },

    scheduleFetch() {
      clearTimeout(this.fetchTimer);
      this.fetchTimer = setTimeout(() => this.fetch(), FETCH_DELAY_MS);
    },

    async fetch() {
      if (!this.view || this.eventsStatus !== "ready") return;
      this.abort?.abort();
      this.abort = new AbortController();
      this.loading = true;
      try {
        const range = {
          t0: this.view.min - this.shift,
          t1: this.view.max - this.shift,
          max_lanes: MAX_LANES,
          filter: this.panel.filter || null,
          group_by: this.groupBy,
        };
        let res;
        if (this.joined) {
          res = await getJSON(`/api/runs/${this.runId}/trace`, range, this.abort.signal);
        } else if (this.logOnF1ap) {
          res = await getJSON(`/api/runs/${this.runId}/trace`, { ...range, sources: [this.panel.source] }, this.abort.signal);
        } else {
          res = await getJSON("/api/trace", { source: this.panel.source, ...range }, this.abort.signal);
        }
        this.error = "";
        this.layout(res);
        await this.$nextTick();
        this.draw();
      } catch (e) {
        if (e.name !== "AbortError") this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    /** Gives each UE its own row, in start order. Events of no UE go to a last row, always shown. */
    layout(res) {
      const shift = this.shift;
      const end = this.source.t_max + shift;
      const rowOfLane = new Map();
      this.lanes = res.lanes.map((lane, row) => {
        rowOfLane.set(lane.lane, row);
        const t0 = lane.t_start + shift;
        const t1 = lane.open ? Math.max(end, lane.t_end + shift) : lane.t_end + shift;
        return { ...lane, t0, t1, row, label: laneLabel(lane, this.groupBy), axisLabel: axisLabel(lane, this.groupBy) };
      });
      this.hasCellRow = res.events.some((e) => e.lane == null);
      this.events = res.events.map((e) => ({ ...e, t: e.t + shift, row: e.lane == null ? -1 : rowOfLane.get(e.lane) ?? -2 }));
      this.nofLanes = res.lanes.length;
      this.totalLanes = res.total_lanes;
      this.truncated = res.truncated;
      const shown = Math.max(1, Math.min(this.nofLanes, VISIBLE_UE_ROWS) + (this.hasCellRow ? 1 : 0));
      this.chartHeight = Math.max(shown, MIN_CHART_ROWS) * ROW_HEIGHT + AXIS_HEIGHT;
      this.scrollHeight = this.chartHeight + Math.max(0, this.nofLanes - VISIBLE_UE_ROWS) * ROW_HEIGHT;
      this.firstRow = Math.min(this.firstRow, Math.max(0, this.nofLanes - VISIBLE_UE_ROWS));
    },

    /** Width of the chart: the one of the plots, so that times line up, also under the scrollbar of the rows. */
    chartWidth() {
      return this.$refs.scroller.offsetWidth;
    },

    /** Number of rows drawn: the UE rows in view and the row of the events of no UE. */
    nofShownRows() {
      return Math.max(1, Math.min(this.nofLanes, VISIBLE_UE_ROWS) + (this.hasCellRow ? 1 : 0));
    },

    /** Drawn row of a UE row, or of the events of no UE for -1, or -1 when out of view. */
    shownRow(row) {
      const ueRows = Math.min(this.nofLanes, VISIBLE_UE_ROWS);
      if (row === -1) return this.hasCellRow ? ueRows : -1;
      const shown = row - this.firstRow;
      return row >= 0 && shown >= 0 && shown < ueRows ? shown : -1;
    },

    /** Labels of the drawn rows. */
    shownLabels() {
      const labels = this.lanes.slice(this.firstRow, this.firstRow + VISIBLE_UE_ROWS).map((lane) => lane.axisLabel);
      if (this.hasCellRow) labels.push("common");
      return labels;
    },

    onScroll() {
      const first = Math.round(this.$refs.scroller.scrollTop / ROW_HEIGHT);
      if (first === this.firstRow) return;
      this.firstRow = first;
      this.chart?.redraw(false, true);
    },

    draw() {
      if (!this.chart) {
        this.chart = this.createChart();
        return;
      }
      if (this.chart.height !== this.chartHeight) this.chart.setSize({ width: this.chartWidth(), height: this.chartHeight });
      this.chart.setData([[this.view.min, this.view.max], [null, null]], false);
      this.chart.setScale("x", { min: this.view.min, max: this.view.max });
      // Rows can change with the same view and count, e.g. another "rows by", which uPlot does not see.
      this.chart.redraw(false, true);
    },

    rebuild() {
      this.chart?.destroy();
      this.chart = null;
      if (this.view) this.draw();
    },

    createChart() {
      const axisColor = cssVar("--fg-muted");
      const gridColor = cssVar("--grid");
      const axis = { stroke: axisColor, grid: { stroke: gridColor, width: 1 }, ticks: { stroke: gridColor, width: 1 } };
      const absolute = this.timeMode === "absolute";
      const opts = {
        width: this.chartWidth(),
        height: this.chartHeight,
        scales: { x: { time: absolute }, y: { range: () => [0, this.nofShownRows()] } },
        tzDate: utcDate,
        legend: { show: false },
        series: [{}, { show: false }],
        axes: [
          absolute ? { ...axis, values: timeTicks, space: TIME_TICK_SPACE } : { ...axis },
          {
            stroke: axisColor,
            size: LABEL_AXIS_SIZE,
            font: "10px sans-serif",
            gap: 4,
            grid: { show: false },
            ticks: { show: false },
            // One split per drawn row at its bar, with the value axis growing upwards.
            splits: () => this.shownLabels().map((_, i) => this.nofShownRows() - i - BAR_POSITION),
            values: () => this.shownLabels(),
          },
        ],
        cursor: { drag: { x: true, y: false, setScale: false }, sync: { key: CURSOR_SYNC_KEY }, points: { show: false } },
        hooks: {
          setSelect: [selectToZoom((range) => this.$emit("zoom", range))],
          setCursor: [(u) => this.updateCursorReadout(u)],
          draw: [(u) => this.drawTrace(u)],
        },
      };
      const chart = new uPlot(opts, [[this.view.min, this.view.max], [null, null]], this.$refs.chart);
      chart.setScale("x", { min: this.view.min, max: this.view.max });
      chart.over.addEventListener("mouseenter", () => { this.hovering = true; });
      chart.over.addEventListener("mouseleave", () => {
        this.hovering = false;
        this.cursorText = "";
      });
      attachZoomPan(chart, (range) => this.$emit("zoom", range), () => this.onClick(chart));
      return chart;
    },

    /** Draws a bar per UE in view from its start to its end, with the glyphs of its events, and the events of no UE. */
    drawTrace(u) {
      const { ctx, bbox } = u;
      const dpr = devicePixelRatio;
      const rowH = bbox.height / this.nofShownRows();
      const rowY = (shown) => bbox.top + (shown + BAR_POSITION) * rowH;
      const left = bbox.left;
      const right = bbox.left + bbox.width;
      const colors = {};
      const color = (category) => (colors[category] ??= cssVar(`--ev-${category}`));
      const glyphR = Math.max(2, Math.min(4, rowH / 4)) * dpr;
      ctx.save();
      ctx.beginPath();
      ctx.rect(left, bbox.top, bbox.width, bbox.height);
      ctx.clip();

      ctx.fillStyle = cssVar("--fg-muted");
      for (const lane of this.lanes) {
        const shown = this.shownRow(lane.row);
        if (shown < 0) continue;
        const x0 = Math.max(left, u.valToPos(lane.t0, "x", true));
        const x1 = Math.min(right, u.valToPos(lane.t1, "x", true));
        if (x1 < left || x0 > right) continue;
        ctx.globalAlpha = lane.open ? 0.35 : 0.55;
        ctx.fillRect(x0, rowY(shown) - 1.5 * dpr, Math.max(dpr, x1 - x0), 3 * dpr);
      }
      ctx.globalAlpha = 1;

      ctx.lineWidth = 1.5 * dpr;
      for (const ev of this.events) {
        const shown = this.shownRow(ev.row);
        if (shown < 0) continue;
        const x = u.valToPos(ev.t, "x", true);
        if (x < left || x > right) continue;
        ctx.fillStyle = ctx.strokeStyle = color(ev.category);
        drawGlyph(ctx, ev.category, x, rowY(shown), glyphR);
      }
      ctx.restore();
    },

    /** Event or UE under a cursor position, in CSS pixels from the top left of the plot area. */
    itemAt(u, left, top) {
      const shown = Math.floor((top / u.over.clientHeight) * this.nofShownRows());
      let best = null;
      let bestDist = EVENT_HIT_PX;
      for (const ev of this.events) {
        if (this.shownRow(ev.row) !== shown) continue;
        const d = Math.abs(u.valToPos(ev.t, "x") - left);
        if (d <= bestDist) {
          best = ev;
          bestDist = d;
        }
      }
      const t = u.posToVal(left, "x");
      const lane = this.lanes.find((l) => this.shownRow(l.row) === shown && l.t0 <= t && t <= l.t1) ?? null;
      return { event: best, lane };
    },

    updateCursorReadout(u) {
      const { left, top } = u.cursor;
      if (left == null || left < 0) {
        this.cursorText = "";
        this.cursorEvent = null;
        this.cursorLane = "";
        return;
      }
      this.cursorText = formatTime(u.posToVal(left, "x"), this.timeMode);
      if (!this.hovering || top == null || top < 0) {
        this.cursorEvent = null;
        this.cursorLane = "";
        return;
      }
      const { event, lane } = this.itemAt(u, left, top);
      this.cursorEvent = event;
      if (lane) {
        const span = lane.open ? "until the end" : `${(lane.t1 - lane.t0).toFixed(3)} s`;
        this.cursorLane = `${lane.label}, ${span}`;
      } else {
        this.cursorLane = event && event.lane == null ? "common" : "";
      }
    },

    onClick(chart) {
      const { left, top } = chart.cursor;
      if (left == null || left < 0 || top == null || top < 0) return;
      const { event } = this.itemAt(chart, left, top);
      if (event) this.$emit("select-record", { source: event.source ?? this.panel.source, record: event.record });
    },
  },
  template: `
    <section class="panel trace">
      <header class="panel-bar">
        <strong>Trace</strong>
        <select v-if="choices && choices.length > 1" v-model.number="panel.source" :title="source ? source.path : 'Source'">
          <option v-for="s in choices" :key="s.id" :value="s.id" :disabled="s.status !== 'ready'">{{ s.file ?? s.name }}</option>
        </select>
        <label class="inline" title="One row per value of an identifier, merging the UE contexts that share it">rows by
          <select :value="groupBy" @change="panel.groupBy = $event.target.value">
            <option v-for="key in groupOptions" :key="key" :value="key">{{ key }}</option>
          </select>
        </label>
        <form class="filter" @submit.prevent="applyFilter">
          <input v-model="filterDraft" :class="{ dirty: filterDirty }" placeholder="rnti == 0x4602 or type == rlf"
                 title="Keeps the events matching comparisons (== != < <= > >=, is null) joined by and/or/not, over type, category, layer, level, ue, rnti, cause and text, and the UEs with such events. Events without ue or rnti take the ones of their UE."
                 @blur="applyFilter" />
        </form>
        <label v-if="source === f1apSource && joinableLogs.length" class="inline muted" title="Join the UE events of the logs of the tab, e.g. random access, to the UE contexts of the F1AP pcap, matched by C-RNTI and time">
          <input type="checkbox" :checked="joined" @change="panel.joined = $event.target.checked" /> log events
        </label>
        <span class="trace-legend">
          <span v-for="g in legend" :key="g.category" :class="'ev-' + g.category"><span class="trace-glyph">{{ g.glyph }}</span>{{ g.label }}</span>
        </span>
        <span class="status">
          <span v-if="eventsStatus !== 'ready'" class="muted">{{ eventsStatus === "error" ? "events could not be parsed" : "parsing events" }}</span>
          <span v-else-if="loading" class="muted">loading</span>
          <span v-else-if="totalLanes > nofLanes" class="muted">first {{ nofLanes }} of {{ totalLanes }} UEs, zoom in for all</span>
          <span v-else class="muted">{{ nofLanes }} UEs{{ scrollable ? ", scroll for more" : "" }}</span>
          <span v-if="truncated" class="muted">, events truncated, zoom in for all</span>
          <span v-if="error" class="error">{{ error }}</span>
        </span>
        <button class="icon" title="Remove trace" @click="$emit('remove')">✕</button>
      </header>
      <p v-for="n in notes" :key="n" class="muted trace-note">{{ n }}</p>
      <div ref="scroller" :class="['trace-scroll', { scrollable }]" :style="{ height: chartHeight + 'px' }" @scroll="onScroll">
        <div :style="{ height: scrollHeight + 'px' }">
          <div class="chart-wrap trace-sticky">
            <div ref="chart" class="chart"></div>
            <div v-if="cursorText" class="cursor-readout">
              {{ cursorText }}<span v-if="cursorLane"> · {{ cursorLane }}</span>
              <div v-if="cursorEvent" :class="['cursor-event', 'ev-' + cursorEvent.category]">
                <span class="event-dot"></span>{{ cursorEvent.type }}: {{ cursorEvent.text }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  `,
};
