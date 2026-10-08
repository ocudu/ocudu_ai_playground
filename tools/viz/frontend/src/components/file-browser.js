// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import { getJSON } from "../api.js";
import { clearRecent, loadRecent } from "../recent.js";

// Characters of a directory shown in the recent files, keeping its end.
const MAX_DIR_CHARS = 60;
// Browser storage key of the last directory browsed.
const LAST_DIR_KEY = "ocudu-viz-last-dir";

/** @param {number | null} bytes */
function formatSize(bytes) {
  if (bytes == null) return "";
  const units = ["B", "kB", "MB", "GB", "TB"];
  let v = bytes;
  let i = 0;
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000;
    i++;
  }
  return `${i ? v.toFixed(1) : v} ${units[i]}`;
}

/**
 * Time since a past moment, e.g. "5 min ago", or its date when older than a week.
 * @param {number} ms Milliseconds since the epoch.
 */
function formatAgo(ms) {
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 7 * 86400) return `${Math.floor(s / 86400)} d ago`;
  return formatDate(ms / 1000);
}

/** @param {number} mtime */
function formatDate(mtime) {
  const d = new Date(mtime * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default {
  name: "FileBrowser",
  props: {
    roots: { type: Array, required: true },
  },
  emits: ["open", "close"],
  data() {
    const recent = loadRecent();
    return { listing: null, error: "", nameFilter: "", showHidden: false, pathInput: "", recent, view: recent.length ? "recent" : "browse" };
  },
  computed: {
    recentEntries() {
      return this.recent.map((e) => {
        const slash = e.path.lastIndexOf("/");
        const dir = e.path.slice(0, slash) || "/";
        return { ...e, name: e.path.slice(slash + 1), dir: dir.length > MAX_DIR_CHARS ? `\u2026${dir.slice(-MAX_DIR_CHARS)}` : dir };
      });
    },
    entries() {
      if (!this.listing) return [];
      const filter = this.nameFilter.trim().toLowerCase();
      return filter ? this.listing.entries.filter((e) => e.name.toLowerCase().includes(filter)) : this.listing.entries;
    },
    /** Path segments of the current directory, each with the path it leads to. */
    crumbs() {
      if (!this.listing) return [];
      const root = this.roots.find((r) => this.listing.path === r || this.listing.path.startsWith(`${r}/`)) ?? "/";
      const crumbs = [{ label: root, path: root }];
      let path = root;
      for (const part of this.listing.path.slice(root.length).split("/").filter(Boolean)) {
        path = `${path.replace(/\/$/, "")}/${part}`;
        crumbs.push({ label: part, path });
      }
      return crumbs;
    },
  },
  mounted() {
    let start = this.roots[0];
    try {
      start = localStorage.getItem(LAST_DIR_KEY) || start;
    } catch {
      // Storage can be unavailable, e.g. in private windows.
    }
    this.browse(start, this.roots[0]);
    this.$refs.filter?.focus();
    this.onKey = (e) => {
      if (e.key === "Escape") this.$emit("close");
    };
    window.addEventListener("keydown", this.onKey);
  },
  beforeUnmount() {
    window.removeEventListener("keydown", this.onKey);
  },
  methods: {
    /**
     * @param {string} path
     * @param {string} [fallback] Directory to show if path cannot be listed.
     */
    async browse(path, fallback) {
      try {
        this.listing = await getJSON("/api/fs", { path, hidden: this.showHidden });
        this.error = "";
        this.nameFilter = "";
        this.pathInput = this.listing.path;
        try {
          localStorage.setItem(LAST_DIR_KEY, this.listing.path);
        } catch {
          // Storage can be unavailable, e.g. in private windows.
        }
      } catch (e) {
        if (fallback && fallback !== path) return this.browse(fallback);
        this.error = e.message;
      }
    },

    activate(entry) {
      const path = `${this.listing.path.replace(/\/$/, "")}/${entry.name}`;
      if (entry.type === "dir") this.browse(path);
      else this.$emit("open", path);
    },

    /** Opens the typed path: a directory is browsed, anything else is opened as a file. */
    async goToPath() {
      const path = this.pathInput.trim();
      if (!path) return;
      try {
        await getJSON("/api/fs", { path });
        this.browse(path);
      } catch {
        this.$emit("open", path);
      }
    },

    clearRecent() {
      clearRecent();
      this.recent = [];
      this.view = "browse";
    },

    toggleHidden() {
      this.showHidden = !this.showHidden;
      if (this.listing) this.browse(this.listing.path);
    },

    formatSize,
    formatDate,
    formatAgo,
  },
  template: `
    <div class="modal-backdrop" @click.self="$emit('close')">
      <section class="modal file-browser" role="dialog" aria-label="Open a file or directory">
        <header class="panel-bar">
          <strong>Open a file or directory</strong>
          <span class="status"></span>
          <button class="icon" title="Close" @click="$emit('close')">✕</button>
        </header>
        <div class="file-browser-body">
          <div class="view-toggle">
            <button :class="{ selected: view === 'recent' }" @click="view = 'recent'">Recent</button>
            <button :class="{ selected: view === 'browse' }" @click="view = 'browse'">Browse</button>
          </div>
          <template v-if="view === 'recent'">
            <p v-if="!recentEntries.length" class="muted">Nothing opened yet.</p>
            <div v-else class="table-scroll file-list">
              <table>
                <tbody>
                  <tr v-for="e in recentEntries" :key="e.path" class="clickable" :title="e.path" @click="$emit('open', e.path, true)">
                    <td>{{ e.dir ? "📁" : "📄" }} {{ e.name }}</td>
                    <td class="muted recent-dir">{{ e.dir }}</td>
                    <td class="muted">{{ formatAgo(e.openedAt) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="recentEntries.length"><button @click="clearRecent">clear</button></div>
          </template>
          <template v-else>
          <form class="path-form" @submit.prevent="goToPath">
            <input v-model="pathInput" class="path-input" placeholder="/path/to/gnb.log" title="Type or paste a file or directory path" />
            <button type="submit">go</button>
          </form>
          <div class="crumbs">
            <template v-for="(c, i) in crumbs" :key="c.path">
              <span v-if="i" class="muted">/</span>
              <a href="#" @click.prevent="browse(c.path)">{{ c.label }}</a>
            </template>
          </div>
          <div class="file-tools">
            <input ref="filter" v-model="nameFilter" placeholder="filter names" />
            <label class="inline muted"><input type="checkbox" :checked="showHidden" @change="toggleHidden" /> hidden files</label>
            <span v-if="roots.length > 1" class="muted">roots:
              <a v-for="r in roots" :key="r" href="#" class="root-link" @click.prevent="browse(r)">{{ r }}</a>
            </span>
          </div>
          <p v-if="error" class="error">{{ error }}</p>
          <div class="table-scroll file-list">
            <table>
              <tbody>
                <tr v-if="listing && listing.parent" class="clickable" @click="browse(listing.parent)">
                  <td>📁 ..</td><td></td><td></td>
                </tr>
                <tr v-for="e in entries" :key="e.name" class="clickable" :title="e.type === 'dir' ? 'Open the directory' : 'Open the file'"
                    @click="activate(e)">
                  <td>{{ e.type === "dir" ? "📁" : "📄" }} {{ e.name }}</td>
                  <td>{{ formatSize(e.size) }}</td>
                  <td class="muted">{{ formatDate(e.mtime) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="listing && listing.truncated" class="muted">Only the first entries are shown, use the filter.</p>
          </template>
        </div>
      </section>
    </div>
  `,
};
