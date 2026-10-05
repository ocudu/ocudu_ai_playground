// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import { createApp } from "vue";
import "uplot/dist/uPlot.min.css";
import "./style.css";
import { getJSON } from "./api.js";
import PlotPanel from "./components/plot-panel.js";
import RecordView from "./components/record-view.js";
import { decodeView, encodeView } from "./view-state.js";

// Delay before writing the view to the URL, to coalesce zoom and pan events.
const URL_UPDATE_DELAY_MS = 300;

let nextPlotId = 1;

/** @param {{source: number, dataset?: string | null} & Record<string, any>} init */
function newPlot(init) {
  return {
    field: null,
    splitBy: null,
    splitValues: [],
    filter: "",
    mode: "time",
    instance: null,
    ...init,
    dataset: init.dataset ?? null,
    id: nextPlotId++,
  };
}

const App = {
  components: { PlotPanel, RecordView },
  data() {
    return { sources: [], plots: [], timeMode: "absolute", userRange: null, selection: null, error: "", warnings: [] };
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
    timeMode() {
      if (!this.restoring) this.userRange = null;
    },
  },
  created() {
    // Not reactive: URL synchronization state.
    this.restoring = false;
    this.urlTimer = null;
    this.writtenHash = "";
  },
  async mounted() {
    try {
      this.sources = await getJSON("/api/sources");
    } catch (e) {
      this.error = e.message;
      return;
    }
    await this.restoreView();
    if (!this.plots.length && this.sources.length) this.plots.push(newPlot({ source: 0 }));

    this.$watch(
      () => [this.plots, this.timeMode, this.userRange],
      () => this.scheduleUrlUpdate(),
      { deep: true },
    );
    // A pasted link only changes the fragment, which does not reload the page.
    window.addEventListener("hashchange", () => {
      if (location.hash !== this.writtenHash) location.reload();
    });
  },
  methods: {
    async restoreView() {
      const restored = decodeView(location.hash, this.sources);
      if (!restored) return;
      this.warnings = restored.warnings;
      const view = restored.view;
      if (!view) return;
      this.restoring = true;
      this.timeMode = view.timeMode === "relative" ? "relative" : "absolute";
      // The range is in display time, which depends on the time mode set above.
      await this.$nextTick();
      this.userRange = view.range && view.range.max > view.range.min ? view.range : null;
      this.plots = view.plots.map((p) => newPlot(p));
      this.restoring = false;
    },

    scheduleUrlUpdate() {
      clearTimeout(this.urlTimer);
      this.urlTimer = setTimeout(() => {
        this.writtenHash = encodeView(this);
        history.replaceState(null, "", this.writtenHash);
      }, URL_UPDATE_DELAY_MS);
    },

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
      <img src="img/ocudu_color.png" alt="OCUDU" class="logo" />
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
      <p v-for="w in warnings" :key="w" class="error">{{ w }}</p>
      <p class="hint muted">Drag to zoom, wheel to zoom, Shift+drag to pan, double-click to reset, click a point to see its log line.</p>
      <plot-panel v-for="p in plots" :key="p.id" :plot="p" :sources="sources" :view="view" :shifts="shifts"
                  :time-mode="timeMode" @zoom="zoom" @remove="removePlot(p.id)" @select-record="selection = $event" />
    </main>
    <record-view v-if="selection" :selection="selection" :sources="sources" @close="selection = null" />
  `,
};

createApp(App).mount("#app");
