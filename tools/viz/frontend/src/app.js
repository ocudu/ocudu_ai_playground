// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import { createApp } from "vue";
import "uplot/dist/uPlot.min.css";
import "./style.css";
import { getJSON } from "./api.js";
import PlotPanel from "./components/plot-panel.js";
import RecordView from "./components/record-view.js";

let nextPlotId = 1;

/** @param {{source: number, dataset?: string | null}} init */
function newPlot(init) {
  return { id: nextPlotId++, source: init.source, dataset: init.dataset ?? null, field: null, groupBy: null, groups: [] };
}

const App = {
  components: { PlotPanel, RecordView },
  data() {
    return { sources: [], plots: [], timeMode: "absolute", userRange: null, selection: null, error: "" };
  },
  computed: {
    /** Shift from source time to display time, per source. */
    shifts() {
      return this.sources.map((s) => (this.timeMode === "relative" ? -(s.t_min ?? 0) : 0));
    },
    fullRange() {
      let min = Infinity;
      let max = -Infinity;
      this.sources.forEach((s, i) => {
        if (s.t_min == null) return;
        min = Math.min(min, s.t_min + this.shifts[i]);
        max = Math.max(max, s.t_max + this.shifts[i]);
      });
      return Number.isFinite(min) ? { min, max: max > min ? max : min + 1 } : null;
    },
    view() {
      return this.userRange ?? this.fullRange;
    },
  },
  watch: {
    timeMode() { this.userRange = null; },
  },
  async mounted() {
    try {
      this.sources = await getJSON("/api/sources");
    } catch (e) {
      this.error = e.message;
      return;
    }
    if (this.sources.length) this.plots.push(newPlot({ source: 0 }));
  },
  methods: {
    addPlot() {
      const last = this.plots[this.plots.length - 1];
      this.plots.push(newPlot(last ? { source: last.source, dataset: last.dataset } : { source: 0 }));
    },
    removePlot(id) {
      this.plots = this.plots.filter((p) => p.id !== id);
    },
    zoom(range) {
      this.userRange = range && range.max > range.min ? range : null;
    },
  },
  template: `
    <header class="app-bar">
      <span class="brand">ocudu-viz</span>
      <div class="spacer"></div>
      <label class="inline">time
        <select v-model="timeMode">
          <option value="absolute">absolute</option>
          <option value="relative">relative</option>
        </select>
      </label>
      <button @click="zoom(null)" :disabled="!userRange">reset zoom</button>
      <button @click="addPlot" :disabled="!sources.length">add plot</button>
    </header>
    <main>
      <p v-if="error" class="error">{{ error }}</p>
      <p class="hint muted">Drag to zoom, wheel to zoom, Shift+drag to pan, double-click to reset, click a point to see its log line.</p>
      <plot-panel v-for="p in plots" :key="p.id" :plot="p" :sources="sources" :view="view" :shifts="shifts"
                  :time-mode="timeMode" @zoom="zoom" @remove="removePlot(p.id)" @select-record="selection = $event" />
    </main>
    <record-view v-if="selection" :selection="selection" :sources="sources" @close="selection = null" />
  `,
};

createApp(App).mount("#app");
