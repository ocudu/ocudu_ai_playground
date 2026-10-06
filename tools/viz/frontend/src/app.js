// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import { createApp } from "vue";
import "uplot/dist/uPlot.min.css";
import "./style.css";
import { getJSON, postJSON } from "./api.js";
import FileBrowser from "./components/file-browser.js";
import PlotPanel from "./components/plot-panel.js";
import RecordView from "./components/record-view.js";
import TablePanel from "./components/table-panel.js";
import TracePanel from "./components/trace-panel.js";
import { applyTheme, loadThemePreference, onSystemThemeChange, saveThemePreference } from "./theme.js";
import { addRecent, removeRecent } from "./recent.js";
import { decodeView, encodeView } from "./view-state.js";

// Event categories, in display order, with their labels.
const EVENT_CATEGORIES = [
  ["ra", "random access"],
  ["lifecycle", "UE lifecycle"],
  ["rrc", "RRC"],
  ["mobility", "mobility"],
  ["failure", "failures"],
  ["warning", "warnings"],
  ["error", "errors"],
];
// Events fetched for the visible window of a tab.
const MAX_EVENTS = 5000;
// Delay before fetching events after the view changes, to coalesce zoom and pan events.
const EVENTS_FETCH_DELAY_MS = 150;
// Interval between refreshes of the sources while some are being parsed.
const SOURCES_POLL_MS = 500;

/** Returns whether a source or its events are still being parsed. */
function isParsing(s) {
  return s.status === "parsing" || (s.status === "ready" && ["pending", "parsing"].includes(s.events_status));
}
// Delay before writing the view to the URL, to coalesce zoom and pan events.
const URL_UPDATE_DELAY_MS = 300;

let nextPlotId = 1;

/**
 * Creates a widget: a plot, a table of a whole dataset with kind "table", or the UE trace with kind "trace".
 * @param {{source: number, dataset?: string | null, kind?: string} & Record<string, any>} init
 */
function newPlot(init) {
  return {
    kind: "plot",
    columnFilter: "",
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

/** State of the tab of one source: its plots, zoom range and shown event categories (null until known). */
function newTab() {
  return { plots: [], userRange: null, defaultPlotAdded: false, eventCategories: [] };
}

const App = {
  components: { FileBrowser, PlotPanel, RecordView, TablePanel, TracePanel },
  data() {
    return {
      sources: [],
      // Tab state by source id.
      tabs: {},
      activeId: null,
      timeMode: "absolute",
      selection: null,
      error: "",
      warnings: [],
      themePref: loadThemePreference(),
      themeVersion: 0,
      roots: [],
      canOpen: false,
      // Events of the visible window of the active tab, in display time.
      events: [],
      eventsTruncated: false,
      browserOpen: false,
    };
  },
  computed: {
    /** Sources shown as tabs, in opening order. */
    openSources() {
      return this.sources.filter((s) => s.status !== "closed");
    },
    activeSource() {
      return this.activeId == null ? null : this.sources[this.activeId];
    },
    activeTab() {
      return this.activeId == null ? null : this.tabs[this.activeId] ?? null;
    },
    /** Shift from source time to display time, per source id. */
    shifts() {
      return this.sources.map((s) => (this.timeMode === "relative" ? -(s.t_min ?? 0) : 0));
    },
    fullRange() {
      const s = this.activeSource;
      if (!s || s.t_min == null) return null;
      const shift = this.shifts[s.id];
      return { min: s.t_min + shift, max: (s.t_max > s.t_min ? s.t_max : s.t_min + 1) + shift };
    },
    /** Inputs of the events request of the active tab. */
    eventsQuery() {
      const s = this.activeSource;
      return [this.activeId, s?.status, s?.events_status, this.view, this.activeTab?.eventCategories, this.timeMode];
    },
    /** Event categories of the active source that have events, with their labels and counts. */
    eventCategoryChips() {
      const counts = this.activeSource?.event_counts ?? {};
      return EVENT_CATEGORIES.filter(([c]) => counts[c]).map(([c, label]) => ({ category: c, label, count: counts[c] }));
    },
    /** Notes about the active source, e.g. why some events are missing. */
    activeNotes() {
      return this.activeSource?.notes ?? [];
    },
    /** State of the events of the active source while they are not ready: "parsing" or "error". */
    eventsState() {
      const s = this.activeSource;
      if (s?.status !== "ready" || s.events_status === "ready") return null;
      return s.events_status === "error" ? "error" : "parsing";
    },
    view() {
      return this.activeTab?.userRange ?? this.fullRange;
    },
    /** Span of the datasets in the plots of the active tab, or of all its datasets without plots. */
    metricsRange() {
      const s = this.activeSource;
      if (!s || s.status !== "ready") return null;
      const names = this.activeTab?.plots.length ? new Set(this.activeTab.plots.map((p) => p.dataset)) : null;
      const spans = s.datasets.filter((d) => d.t_min != null && (!names || names.has(d.name))).map((d) => [d.t_min, d.t_max]);
      if (!spans.length) return null;
      const shift = this.shifts[s.id];
      const min = Math.min(...spans.map((x) => x[0])) + shift;
      const max = Math.max(...spans.map((x) => x[1])) + shift;
      return { min, max: max > min ? max : min + 1 };
    },
  },
  watch: {
    themePref(pref) {
      saveThemePreference(pref);
      applyTheme(pref);
      this.themeVersion++;
    },
    timeMode() {
      // Zoom ranges are in display time, which the time mode changes.
      if (this.restoring) return;
      for (const tab of Object.values(this.tabs)) tab.userRange = null;
    },
    activeId() {
      this.selection = null;
    },
    eventsQuery: {
      handler() {
        clearTimeout(this.eventsTimer);
        this.eventsTimer = setTimeout(() => this.fetchEvents(), EVENTS_FETCH_DELAY_MS);
      },
      deep: true,
    },
  },
  created() {
    // Not reactive: URL synchronization state.
    this.restoring = false;
    this.urlTimer = null;
    this.writtenHash = "";
    // Polling of the sources while some are being parsed.
    this.pollTimer = null;
    // Pending and in-flight events requests.
    this.eventsTimer = null;
    this.eventsAbort = null;
    // Ids of the sources whose parsing error was already reported.
    this.reportedErrors = new Set();
    applyTheme(this.themePref);
    onSystemThemeChange(() => {
      if (this.themePref !== "auto") return;
      applyTheme("auto");
      this.themeVersion++;
    });
  },
  async mounted() {
    try {
      const [sources, roots] = await Promise.all([getJSON("/api/sources"), getJSON("/api/roots")]);
      this.sources = sources;
      this.roots = roots.roots;
      this.canOpen = roots.can_open;
    } catch (e) {
      this.error = e.message;
      return;
    }
    await this.restoreView();
    this.syncTabs();
    if (this.openSources.some(isParsing)) this.pollSources();

    this.$watch(
      () => [this.tabs, this.activeId, this.timeMode],
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
      const restored = decodeView(location.hash, this.openSources);
      if (!restored) return;
      this.warnings = restored.warnings;
      const view = restored.view;
      if (!view) return;
      this.restoring = true;
      this.timeMode = view.timeMode === "relative" ? "relative" : "absolute";
      // Zoom ranges are in display time, which depends on the time mode set above.
      await this.$nextTick();
      for (const t of view.tabs) {
        const tab = newTab();
        tab.userRange = t.range && t.range.max > t.range.min ? t.range : null;
        tab.plots = t.plots.map((p) => newPlot({ ...p, source: t.source }));
        tab.eventCategories = t.eventCategories ?? [];
        tab.defaultPlotAdded = true;
        this.tabs[t.source] = tab;
      }
      if (view.active != null) this.activeId = view.active;
      this.restoring = false;
    },

    scheduleUrlUpdate() {
      clearTimeout(this.urlTimer);
      this.urlTimer = setTimeout(() => {
        this.writtenHash = encodeView(this);
        history.replaceState(null, "", this.writtenHash);
      }, URL_UPDATE_DELAY_MS);
    },

    /** Creates the tabs of new sources, drops the ones of closed sources, and keeps a tab selected. */
    syncTabs() {
      const open = new Set(this.openSources.map((s) => s.id));
      for (const id of Object.keys(this.tabs)) {
        if (!open.has(Number(id))) delete this.tabs[id];
      }
      for (const s of this.openSources) {
        if (!this.tabs[s.id]) this.tabs[s.id] = newTab();
        const tab = this.tabs[s.id];
        // A parsed source starts with one plot, once, so that removing all plots is not undone.
        if (s.status === "ready" && !tab.defaultPlotAdded) {
          tab.defaultPlotAdded = true;
          addRecent(s.path);
          if (!tab.plots.length) tab.plots.push(newPlot({ source: s.id }));
        }
      }
      if (this.activeId == null || !open.has(this.activeId)) this.activeId = this.openSources[0]?.id ?? null;
    },

    /** @param {string} category */
    toggleEventCategory(category) {
      const tab = this.activeTab;
      const shown = new Set(tab.eventCategories ?? []);
      if (shown.has(category)) shown.delete(category);
      else shown.add(category);
      tab.eventCategories = EVENT_CATEGORIES.map(([c]) => c).filter((c) => shown.has(c));
    },

    /** Fetches the events of the visible window of the active tab, in the shown categories. */
    async fetchEvents() {
      this.eventsAbort?.abort();
      const s = this.activeSource;
      const categories = this.activeTab?.eventCategories;
      if (!s || s.status !== "ready" || !categories?.length || !this.view) {
        this.events = [];
        this.eventsTruncated = false;
        return;
      }
      this.eventsAbort = new AbortController();
      const shift = this.shifts[s.id];
      try {
        const res = await getJSON(
          "/api/events",
          { source: s.id, t0: this.view.min - shift, t1: this.view.max - shift, categories, limit: MAX_EVENTS },
          this.eventsAbort.signal,
        );
        this.events = res.events.map((e) => ({ ...e, t: e.t + shift }));
        this.eventsTruncated = res.truncated;
      } catch (e) {
        if (e.name !== "AbortError") this.warnings = [...this.warnings, e.message];
      }
    },

    /** @param {"plot" | "table" | "trace"} kind */
    async addPlot(kind) {
      const tab = this.activeTab;
      if (!tab) return;
      const last = tab.plots.findLast((p) => p.dataset);
      tab.plots.push(newPlot({ source: this.activeId, dataset: kind === "trace" ? null : last?.dataset, kind }));
      await this.$nextTick();
      [...document.querySelectorAll("main > .panel")].at(-1)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    },

    removePlot(id) {
      this.activeTab.plots = this.activeTab.plots.filter((p) => p.id !== id);
    },

    zoom(range) {
      if (this.activeTab) this.activeTab.userRange = range && range.max > range.min ? range : null;
    },

    /**
     * Opens a file in its own tab and selects it. A file that is already open just gets its tab selected.
     * @param {string} path
     * @param {boolean} [fromRecent] Whether the path comes from the recent files, which drop it if it fails.
     */
    async openFile(path, fromRecent = false) {
      this.browserOpen = false;
      let source;
      try {
        source = await postJSON("/api/sources", { path });
      } catch (e) {
        if (fromRecent) removeRecent(path);
        this.warnings = [...this.warnings, fromRecent ? `${e.message} It was removed from the recent files.` : e.message];
        return;
      }
      await this.pollSources();
      this.activeId = source.id;
    },

    async closeTab(id) {
      try {
        await fetch(`/api/sources/${id}`, { method: "DELETE" });
      } catch (e) {
        this.warnings = [...this.warnings, e.message];
      }
      const order = this.openSources.map((s) => s.id);
      const next = order[order.indexOf(id) + 1] ?? order[order.indexOf(id) - 1] ?? null;
      if (this.activeId === id) this.activeId = next;
      await this.pollSources();
    },

    /** Refreshes the sources, and again shortly after while some sources or their events are being parsed. */
    async pollSources() {
      clearTimeout(this.pollTimer);
      try {
        this.sources = await getJSON("/api/sources");
      } catch (e) {
        this.error = e.message;
        return;
      }
      for (const s of this.sources) {
        if (s.status === "error" && !this.reportedErrors.has(s.id)) {
          this.reportedErrors.add(s.id);
          this.warnings = [...this.warnings, s.error];
        }
      }
      this.syncTabs();
      if (this.openSources.some(isParsing)) {
        this.pollTimer = setTimeout(() => this.pollSources(), SOURCES_POLL_MS);
      }
    },
  },
  template: `
    <header class="app-bar">
      <img src="img/ocudu_color.png" alt="OCUDU" class="logo" />
      <nav class="tabs" role="tablist">
        <div v-for="s in openSources" :key="s.id" role="tab" :aria-selected="s.id === activeId"
             :class="['tab', s.status, { active: s.id === activeId }]" :title="s.status === 'error' ? s.error : s.path"
             @click="activeId = s.id">
          <span>{{ s.name }}</span>
          <span v-if="s.status === 'parsing'" class="muted">{{ Math.floor(s.progress * 100) }}%</span>
          <button class="icon tab-close" title="Close the file" @click.stop="closeTab(s.id)">✕</button>
        </div>
        <button class="tab tab-new" :disabled="!canOpen" title="Open a log file in a new tab" @click="browserOpen = true">+</button>
      </nav>
      <div class="spacer"></div>
      <label class="inline">time
        <select v-model="timeMode">
          <option value="absolute">absolute</option>
          <option value="relative">relative</option>
        </select>
      </label>
      <label class="inline">theme
        <select v-model="themePref">
          <option value="auto">auto</option>
          <option value="light">light</option>
          <option value="dark">dark</option>
        </select>
      </label>
      <button @click="zoom(null)" :disabled="!activeTab || !activeTab.userRange" title="Show the whole time range of the log">reset zoom</button>
      <button @click="zoom(metricsRange)" :disabled="!metricsRange" title="Fit the time range of the plotted metrics">fit metrics</button>
    </header>
    <main>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-for="w in warnings" :key="w" class="error">{{ w }}</p>
      <div v-if="!openSources.length && !error" class="empty-state">
        <p>No log files are open yet.</p>
        <button @click="browserOpen = true" :disabled="!canOpen">Open a log file</button>
      </div>
      <div v-else-if="activeSource && activeSource.status === 'parsing'" class="empty-state">
        <p>Parsing {{ activeSource.name }}: {{ Math.floor(activeSource.progress * 100) }}%</p>
        <p class="muted">{{ activeSource.path }}</p>
      </div>
      <div v-else-if="activeSource && activeSource.status === 'error'" class="empty-state">
        <p class="error">{{ activeSource.error }}</p>
      </div>
      <template v-else-if="activeTab">
        <p class="hint muted">Drag to zoom, wheel to zoom, Shift+drag to pan, double-click to reset, click a point or an event marker to see its log line.</p>
        <div v-if="eventCategoryChips.length || eventsState || activeNotes.length" class="event-bar">
          <span class="muted">events</span>
          <span v-if="eventsState === 'parsing'" class="muted">parsing…</span>
          <span v-else-if="eventsState === 'error'" class="error">could not be parsed</span>
          <button v-for="c in eventCategoryChips" :key="c.category"
                  :class="['event-chip', 'ev-' + c.category, { off: !(activeTab.eventCategories || []).includes(c.category) }]"
                  :title="'Show or hide the ' + c.label + ' events'" @click="toggleEventCategory(c.category)">
            <span class="event-dot"></span>{{ c.label }} <span class="muted">{{ c.count }}</span>
          </button>
          <span v-if="eventsTruncated" class="muted">only the first {{ events.length }} events of the window are shown, zoom in for all</span>
          <span v-for="n in activeNotes" :key="n" class="muted event-note">{{ n }}</span>
        </div>
        <template v-for="p in activeTab.plots" :key="p.id">
          <trace-panel v-if="p.kind === 'trace'" :panel="p" :sources="sources" :view="view" :shifts="shifts" :time-mode="timeMode"
                       :theme-version="themeVersion" @zoom="zoom" @remove="removePlot(p.id)" @select-record="selection = $event" />
          <table-panel v-else-if="p.kind === 'table'" :panel="p" :sources="sources" :view="view" :shifts="shifts" :show-source="false"
                       @remove="removePlot(p.id)" @select-record="selection = $event" />
          <plot-panel v-else :plot="p" :sources="sources" :view="view" :shifts="shifts" :time-mode="timeMode"
                      :theme-version="themeVersion" :show-source="false" :events="events"
                      @zoom="zoom" @remove="removePlot(p.id)" @select-record="selection = $event" />
        </template>
        <div class="add-buttons">
          <button class="add-plot" title="Plot of a metric over time, or its histogram" @click="addPlot('plot')">+ plot</button>
          <button class="add-plot" title="Table of all the metrics of a layer" @click="addPlot('table')">+ table</button>
          <button class="add-plot" title="Timeline of each UE, with its events" @click="addPlot('trace')">+ trace</button>
        </div>
      </template>
    </main>
    <record-view v-if="selection" :selection="selection" :sources="sources" @close="selection = null" />
    <file-browser v-if="browserOpen" :roots="roots" @open="openFile" @close="browserOpen = false" />
  `,
};

createApp(App).mount("#app");
