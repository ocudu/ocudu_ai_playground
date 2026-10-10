// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import { getJSON } from "../api.js";
import EventTables from "./event-tables.js";

// Records shown around the selected one.
const WINDOW = 61;
// Browser storage key of the height of the log lines, in pixels.
const HEIGHT_KEY = "ocudu-viz-log-height";
const MIN_HEIGHT = 80;
// Maximum height, as a fraction of the window height.
const MAX_HEIGHT_FRACTION = 0.85;

/** @returns {number | null} */
function loadHeight() {
  try {
    const h = Number(localStorage.getItem(HEIGHT_KEY));
    return h > 0 ? h : null;
  } catch {
    // Storage can be unavailable, e.g. in private windows.
    return null;
  }
}

/** @param {number | null} height */
function saveHeight(height) {
  try {
    if (height == null) localStorage.removeItem(HEIGHT_KEY);
    else localStorage.setItem(HEIGHT_KEY, String(Math.round(height)));
  } catch {
    // Storage can be unavailable, e.g. in private windows.
  }
}

export default {
  name: "RecordView",
  props: {
    selection: { type: Object, required: true },
    sources: { type: Array, required: true },
  },
  components: { EventTables },
  emits: ["close"],
  data() {
    // current is the highlighted record, the selected one until another record is clicked, and detail its decoding.
    return {
      records: [], center: 0, error: "", height: loadHeight(), current: null, detail: "", detailError: "",
      // Decoded record as a structure, for sources that give one, and the view of it: "decisions", "events" or "raw".
      detailData: null, detailTab: "decisions",
      // Search of the records: its text, whether it is a regular expression, and its outcome, e.g. "no match".
      query: "", regex: false, searchNote: "", searching: false,
    };
  },
  computed: {
    source() {
      return this.sources[this.selection.source];
    },
    sourceName() {
      return this.source?.name ?? "";
    },
    /** Matcher of the search in the shown lines, to highlight its matches, or null. JavaScript regular expressions
     * mostly agree with the Python ones of the server; a pattern only the server takes is not highlighted. */
    hitPattern() {
      if (!this.query) return null;
      try {
        return new RegExp(this.regex ? this.query : this.query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
      } catch {
        return null;
      }
    },
    /** Whether records decode, e.g. pcap frames, which are then shown beside the records. */
    hasDetail() {
      return Boolean(this.source?.has_detail);
    },
  },
  watch: {
    selection: {
      handler() {
        this.current = this.selection.record;
        // An allocation picked in the resource grid shows in the decisions of its slot.
        if (this.selection.item) this.detailTab = "decisions";
        this.load(this.selection.record);
        this.loadDetail();
      },
      immediate: true,
      deep: true,
    },
  },
  methods: {
    /** Highlights a record and shows its decoding, for sources whose records decode. */
    select(record) {
      if (!this.hasDetail) return;
      this.current = record;
      this.loadDetail();
    },

    async loadDetail() {
      this.detail = "";
      this.detailData = null;
      this.detailError = "";
      if (!this.hasDetail) return;
      const record = this.current;
      try {
        const res = await getJSON("/api/records/detail", { source: this.selection.source, record });
        if (record === this.current) {
          this.detail = res.text;
          this.detailData = res.data ?? null;
        }
      } catch (e) {
        this.detailError = e.message;
      }
    },

    /** Resizes the log lines by dragging the top edge of the pane. */
    startResize(e) {
      e.preventDefault();
      const handle = e.currentTarget;
      handle.setPointerCapture(e.pointerId);
      const startY = e.clientY;
      const startHeight = this.$refs.lines.offsetHeight;
      const onMove = (ev) => {
        const max = window.innerHeight * MAX_HEIGHT_FRACTION;
        this.height = Math.min(max, Math.max(MIN_HEIGHT, startHeight + startY - ev.clientY));
      };
      const onUp = () => {
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onUp);
        saveHeight(this.height);
      };
      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onUp);
    },

    /**
     * Splits the text of a record at its marks, which are [start, end) spans.
     * @returns {{text: string, mark: boolean}[]}
     */
    segments(r) {
      const parts = [];
      let pos = 0;
      for (const [start, end] of this.spans(r)) {
        if (start > pos) parts.push({ text: r.text.slice(pos, start), mark: false });
        parts.push({ text: r.text.slice(start, end), mark: true });
        pos = end;
      }
      if (pos < r.text.length || !parts.length) parts.push({ text: r.text.slice(pos), mark: false });
      return parts;
    },

    /** Marks of a record: the spans of its field, and the matches of the search, sorted and without overlaps. */
    spans(r) {
      const spans = [...(r.marks ?? [])];
      const hit = this.hitPattern;
      if (hit) {
        for (const m of r.text.matchAll(hit)) {
          if (m[0].length) spans.push([m.index, m.index + m[0].length]);
        }
      }
      spans.sort((a, b) => a[0] - b[0]);
      const out = [];
      for (const s of spans) {
        if (out.length && s[0] < out[out.length - 1][1]) out[out.length - 1][1] = Math.max(out[out.length - 1][1], s[1]);
        else out.push([...s]);
      }
      return out;
    },

    /** Goes to the next record matching the search after the highlighted one, or the previous one with backward. */
    async search(backward = false) {
      if (!this.query || this.searching) return;
      this.searching = true;
      try {
        const res = await getJSON("/api/records/search", {
          source: this.selection.source, q: this.query, regex: this.regex, after: this.current ?? this.center, backward,
        });
        this.searchNote = res.record == null ? "no match" : res.wrapped ? (backward ? "wrapped to the end" : "wrapped to the start") : "";
        if (res.record != null) {
          this.current = res.record;
          await this.load(res.record);
          this.loadDetail();
        }
      } catch (e) {
        this.searchNote = e.message;
      } finally {
        this.searching = false;
      }
    },

    resetHeight() {
      this.height = null;
      saveHeight(null);
    },

    async load(center) {
      this.center = Math.max(1, center);
      try {
        const { source, record, field } = this.selection;
        this.records = await getJSON("/api/records", { source, around: this.center, count: WINDOW, mark: field ? record : null, field });
        this.error = "";
      } catch (e) {
        this.error = e.message;
      }
      await this.$nextTick();
      // Only the log lines scroll: scrollIntoView would also scroll the page, moving the clicked plot away.
      const lines = this.$refs.lines;
      const selected = lines?.querySelector(".record-line.selected");
      if (selected) lines.scrollTop = selected.offsetTop - (lines.clientHeight - selected.offsetHeight) / 2;
      const mark = selected?.querySelector("mark");
      if (mark) {
        // Marks near the end of long lines would be out of view.
        const left = mark.getBoundingClientRect().left - lines.getBoundingClientRect().left + lines.scrollLeft;
        if (left < lines.scrollLeft || left + mark.offsetWidth > lines.scrollLeft + lines.clientWidth) {
          lines.scrollLeft = Math.max(0, left - lines.clientWidth / 3);
        }
      }
    },
  },
  template: `
    <aside class="records">
      <div class="resize-handle" title="Drag to resize, double-click to reset" @pointerdown="startResize" @dblclick="resetHeight"></div>
      <header class="panel-bar">
        <strong>{{ sourceName }}</strong>
        <span class="muted">{{ hasDetail ? "frame" : "line" }} {{ current }}</span>
        <button @click="load(center - WINDOW)">earlier</button>
        <button @click="load(center + WINDOW)">later</button>
        <form class="filter record-search" @submit.prevent="search(false)">
          <input v-model="query" placeholder="search" title="Enter: next match, Shift+Enter: previous. Case-insensitive."
                 @keydown.enter.shift.prevent="search(true)" @input="searchNote = ''" />
        </form>
        <label class="inline" title="Search with a regular expression (Python syntax), e.g. ue=\d+ .*RLF">
          <input type="checkbox" v-model="regex" @change="searchNote = ''" /> regex
        </label>
        <button class="icon" title="Previous match (Shift+Enter)" :disabled="!query" @click="search(true)">↑</button>
        <button class="icon" title="Next match (Enter)" :disabled="!query" @click="search(false)">↓</button>
        <span v-if="searching" class="muted">searching</span>
        <span v-else-if="searchNote" :class="searchNote === 'no match' || searchNote.startsWith('wrapped') ? 'muted' : 'error'">{{ searchNote }}</span>
        <span class="status"><span v-if="error" class="error">{{ error }}</span></span>
        <button class="icon" title="Close" @click="$emit('close')">✕</button>
      </header>
      <div :class="['record-body', { split: hasDetail }]">
        <div ref="lines" class="record-lines" :style="height ? { height: height + 'px' } : null">
          <div v-for="r in records" :key="r.record"
               :class="['record-line', { selected: r.record === current, clickable: hasDetail }]" @click="select(r.record)">
            <span class="lineno">{{ r.record }}</span><span class="text"><template v-for="(part, i) in segments(r)" :key="i"><mark v-if="part.mark">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span>
          </div>
        </div>
        <div v-if="hasDetail && detailData" class="record-detail record-detail-tabs" :style="height ? { height: height + 'px' } : null">
          <div class="detail-tabs">
            <button v-for="tab in ['decisions', 'events', 'raw']" :key="tab" :class="{ active: detailTab === tab }" @click="detailTab = tab">{{ tab }}</button>
          </div>
          <pre v-if="detailTab === 'raw'">{{ detail }}</pre>
          <event-tables v-else :event="detailData" :view="detailTab" :slots-per-frame="source?.grid?.slots_per_frame ?? null"
                        :highlight="current === selection.record ? selection.item ?? null : null" />
        </div>
        <pre v-else-if="hasDetail" class="record-detail" :style="height ? { height: height + 'px' } : null"><span v-if="detailError" class="error">{{ detailError }}</span>{{ detail || (detailError ? "" : "decoding…") }}</pre>
      </div>
    </aside>
  `,
};
