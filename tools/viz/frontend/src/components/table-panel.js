// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import uPlot from "uplot";
import { buildQuery, getJSON } from "../api.js";
import { displayUnit, formatStat } from "../units.js";

// Rows shown in the table, the CSV export has all of them.
const TABLE_ROWS = 1000;
// Delay before fetching after the view changes, to coalesce zoom and pan events.
const FETCH_DELAY_MS = 150;
// Characters of a list value shown in a cell, the full value is in its tooltip.
const MAX_CELL_CHARS = 40;

const fmtTime = uPlot.fmtDate("{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}.{fff}");

/** @param {number} ts */
function formatTime(ts) {
  return fmtTime(uPlot.tzDate(new Date(ts * 1e3), "Etc/UTC"));
}

export default {
  name: "TablePanel",
  props: {
    panel: { type: Object, required: true },
    sources: { type: Array, required: true },
    view: { type: Object, default: null },
    shifts: { type: Array, required: true },
    // Whether the panel shows a source selector, which is not needed when the source is fixed, e.g. by a tab.
    showSource: { type: Boolean, default: true },
  },
  emits: ["remove", "select-record"],
  data() {
    return { loading: false, error: "", fields: [], rows: [], total: 0, instanceOptions: [], filterDraft: this.panel.filter };
  },
  computed: {
    source() {
      return this.sources[this.panel.source];
    },
    datasets() {
      return this.source ? this.source.datasets : [];
    },
    dataset() {
      return this.datasets.find((d) => d.name === this.panel.dataset);
    },
    shift() {
      return this.shifts[this.panel.source] || 0;
    },
    /** Indexes of the fields shown: context fields, and the metrics matching any word of the column filter. */
    shownColumns() {
      const terms = this.panel.columnFilter.toLowerCase().split(/\s+/).filter(Boolean);
      const shown = [];
      this.fields.forEach((f, i) => {
        if (f.context || !terms.length || terms.some((t) => f.name.toLowerCase().includes(t))) shown.push(i);
      });
      return shown;
    },
    /** Display unit of each numeric field, scaled to the values of the loaded rows. */
    columnUnits() {
      return this.fields.map((f, i) => {
        if (f.type !== "number" || !f.unit) return { divisor: 1, label: f.unit || "" };
        let maxAbs = 0;
        for (const r of this.rows) {
          const v = r[i + 2];
          if (typeof v === "number") maxAbs = Math.max(maxAbs, Math.abs(v));
        }
        return displayUnit(f.unit, maxAbs);
      });
    },
    nofMetricColumns() {
      return this.fields.filter((f) => !f.context).length;
    },
    nofShownMetricColumns() {
      return this.shownColumns.filter((i) => !this.fields[i].context).length;
    },
    csvHref() {
      const fields = this.shownColumns.map((i) => this.fields[i].name);
      return `/api/table.csv?${buildQuery({ ...this.queryParams(), fields })}`;
    },
    filterDirty() {
      return this.filterDraft.trim() !== this.panel.filter;
    },
  },
  watch: {
    "panel.source"() {
      this.panel.dataset = this.datasets[0]?.name ?? null;
      this.loadInstanceOptions(true);
    },
    "panel.dataset"() {
      this.loadInstanceOptions(true);
    },
    view: { handler() { this.scheduleFetch(); }, deep: true },
  },
  created() {
    // Not reactive: request state.
    this.fetchTimer = null;
    this.abort = null;
    this.$watch(
      () => [this.panel.source, this.panel.dataset, this.panel.instance, this.panel.filter, this.shift],
      () => this.scheduleFetch(),
    );
  },
  mounted() {
    if (!this.panel.dataset) this.panel.dataset = this.datasets[0]?.name ?? null;
    this.loadInstanceOptions(this.panel.instance == null);
    this.scheduleFetch();
  },
  beforeUnmount() {
    clearTimeout(this.fetchTimer);
    this.abort?.abort();
  },
  methods: {
    queryParams() {
      const params = {
        source: this.panel.source,
        dataset: this.panel.dataset,
        filter: this.panel.filter || null,
        instance: this.dataset?.instance ? this.panel.instance : null,
      };
      if (this.view) {
        params.t0 = this.view.min - this.shift;
        params.t1 = this.view.max - this.shift;
      }
      return params;
    },

    scheduleFetch() {
      clearTimeout(this.fetchTimer);
      this.fetchTimer = setTimeout(() => this.fetch(), FETCH_DELAY_MS);
    },

    async fetch() {
      if (!this.panel.dataset) return;
      this.abort?.abort();
      this.abort = new AbortController();
      this.loading = true;
      try {
        const res = await getJSON("/api/table", { ...this.queryParams(), limit: TABLE_ROWS }, this.abort.signal);
        this.fields = res.fields;
        this.rows = res.rows;
        this.total = res.total;
        this.error = "";
      } catch (e) {
        if (e.name !== "AbortError") this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    /** @param {boolean} selectFirst Whether to select the first instance, e.g. after a dataset change. */
    async loadInstanceOptions(selectFirst) {
      this.instanceOptions = [];
      if (!this.dataset?.instance) {
        this.panel.instance = null;
        return;
      }
      const dataset = this.panel.dataset;
      try {
        const values = await getJSON("/api/context", { source: this.panel.source, dataset, field: this.dataset.instance });
        // The dataset may have changed while the request was in flight.
        if (dataset !== this.panel.dataset) return;
        this.instanceOptions = values.map(String);
        if (selectFirst) this.panel.instance = this.instanceOptions[0] ?? null;
      } catch (e) {
        this.error = e.message;
      }
    },

    applyFilter() {
      this.panel.filter = this.filterDraft.trim();
    },

    header(i) {
      const unit = this.columnUnits[i].label;
      return unit ? `${this.fields[i].name} [${unit}]` : this.fields[i].name;
    },

    cell(row, i) {
      const v = row[i + 2];
      if (v == null) return "–";
      if (typeof v === "number") return formatStat(v / this.columnUnits[i].divisor);
      const text = String(v);
      return text.length > MAX_CELL_CHARS ? `${text.slice(0, MAX_CELL_CHARS)}…` : text;
    },

    formatTime,
  },
  template: `
    <section class="panel">
      <header class="panel-bar">
        <select v-if="showSource" v-model.number="panel.source" :title="source ? source.path : 'Source'">
          <option v-for="s in sources" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <select v-model="panel.dataset" title="Dataset">
          <option v-for="d in datasets" :key="d.name" :value="d.name">{{ d.label }}</option>
        </select>
        <select v-if="dataset && dataset.instance" v-model="panel.instance" :title="dataset.instance">
          <option :value="null">all</option>
          <option v-for="v in instanceOptions" :key="v" :value="v">{{ v }}</option>
        </select>
        <input v-model="panel.columnFilter" class="column-filter" placeholder="columns, e.g. latency brate"
               title="Shows the metric columns whose name contains any of the words" />
        <form class="filter" @submit.prevent="applyFilter">
          <input v-model="filterDraft" :class="{ dirty: filterDirty }" placeholder="rnti > 0x4605 and pci == 1"
                 title="Row filter: comparisons (== != < <= > >=, is null) joined by and/or/not. Values in base units (us, bps)." @blur="applyFilter" />
        </form>
        <span class="status">
          <span v-if="loading" class="muted">loading</span>
          <span v-if="error" class="error">{{ error }}</span>
        </span>
        <a class="button" :href="csvHref" download title="All rows of the visible window and the shown columns, values in the canonical unit">export CSV</a>
        <button class="icon" title="Remove table" @click="$emit('remove')">✕</button>
      </header>
      <div class="table-view">
        <div class="table-bar muted">
          {{ rows.length < total ? "first " + rows.length.toLocaleString() + " of " : "" }}{{ total.toLocaleString() }} rows in the visible window,
          {{ nofShownMetricColumns }} of {{ nofMetricColumns }} metric columns
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr><th>time (UTC)</th><th>line</th><th v-for="i in shownColumns" :key="fields[i].name">{{ header(i) }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r[1]" class="clickable" title="Show the log line"
                  @click="$emit('select-record', { source: panel.source, record: r[1] })">
                <td>{{ formatTime(r[0]) }}</td><td>{{ r[1] }}</td>
                <td v-for="i in shownColumns" :key="fields[i].name" :title="typeof r[i + 2] === 'string' ? r[i + 2] : undefined"
                    @click.stop="$emit('select-record', { source: panel.source, record: r[1], field: fields[i].name })">{{ cell(r, i) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  `,
};
