// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import { getJSON } from "../api.js";

// Records shown around the selected one.
const WINDOW = 61;

export default {
  name: "RecordView",
  props: {
    selection: { type: Object, required: true },
    sources: { type: Array, required: true },
  },
  emits: ["close"],
  data() {
    return { records: [], center: 0, error: "" };
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
    async load(center) {
      this.center = Math.max(1, center);
      try {
        this.records = await getJSON("/api/records", { source: this.selection.source, around: this.center, count: WINDOW });
        this.error = "";
      } catch (e) {
        this.error = e.message;
      }
      await this.$nextTick();
      this.$el.querySelector(".record-line.selected")?.scrollIntoView({ block: "center" });
    },
  },
  template: `
    <aside class="records">
      <header class="panel-bar">
        <strong>{{ sourceName }}</strong>
        <span class="muted">line {{ selection.record }}</span>
        <button @click="load(center - WINDOW)">earlier</button>
        <button @click="load(center + WINDOW)">later</button>
        <span v-if="error" class="error">{{ error }}</span>
        <button class="icon" title="Close" @click="$emit('close')">✕</button>
      </header>
      <div class="record-lines">
        <div v-for="r in records" :key="r.record"
             :class="['record-line', { selected: r.record === selection.record }]">
          <span class="lineno">{{ r.record }}</span><span class="text">{{ r.text }}</span>
        </div>
      </div>
    </aside>
  `,
};
