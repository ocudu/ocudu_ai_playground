// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import { getJSON } from "../api.js";

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
  emits: ["close"],
  data() {
    return { records: [], center: 0, error: "", height: loadHeight() };
  },
  computed: {
    sourceName() {
      return this.sources[this.selection.source]?.name ?? "";
    },
  },
  watch: {
    selection: { handler() { this.load(this.selection.record); }, immediate: true, deep: true },
  },
  methods: {
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
      for (const [start, end] of r.marks ?? []) {
        if (start > pos) parts.push({ text: r.text.slice(pos, start), mark: false });
        parts.push({ text: r.text.slice(start, end), mark: true });
        pos = end;
      }
      if (pos < r.text.length || !parts.length) parts.push({ text: r.text.slice(pos), mark: false });
      return parts;
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
        <span class="muted">line {{ selection.record }}</span>
        <button @click="load(center - WINDOW)">earlier</button>
        <button @click="load(center + WINDOW)">later</button>
        <span v-if="error" class="error">{{ error }}</span>
        <button class="icon" title="Close" @click="$emit('close')">✕</button>
      </header>
      <div ref="lines" class="record-lines" :style="height ? { height: height + 'px' } : null">
        <div v-for="r in records" :key="r.record"
             :class="['record-line', { selected: r.record === selection.record }]">
          <span class="lineno">{{ r.record }}</span><span class="text"><template v-for="(part, i) in segments(r)" :key="i"><mark v-if="part.mark">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span>
        </div>
      </div>
    </aside>
  `,
};
