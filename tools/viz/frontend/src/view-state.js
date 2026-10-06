// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

// Bumped when the encoded state changes incompatibly.
const VERSION = 2;
const PREFIX = "#v=";
// Plot properties saved in the view state. A plot's source is the source of its tab.
const PLOT_KEYS = ["kind", "dataset", "instance", "field", "splitBy", "splitValues", "filter", "mode", "columnFilter"];

/** @param {string} text */
function toBase64Url(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** @param {string} encoded */
function fromBase64Url(encoded) {
  const binary = atob(encoded.replace(/-/g, "+").replace(/_/g, "/"));
  return new TextDecoder().decode(Uint8Array.from(binary, (c) => c.charCodeAt(0)));
}

/**
 * Encodes the view as a URL fragment: the open tabs with their plots and zoom, and the selected tab.
 * Sources are identified by name, not path.
 * @param {{openSources: Array<{id: number, name: string}>, sources: Array<{name: string}>, tabs: Record<number, any>, activeId: number | null, timeMode: string}} app
 */
export function encodeView(app) {
  const state = {
    v: VERSION,
    timeMode: app.timeMode,
    active: app.activeId == null ? null : app.sources[app.activeId]?.name ?? null,
    tabs: app.openSources
      .filter((s) => app.tabs[s.id])
      .map((s) => ({
        source: s.name,
        range: app.tabs[s.id].userRange,
        events: app.tabs[s.id].eventCategories,
        plots: app.tabs[s.id].plots.map((p) => Object.fromEntries(PLOT_KEYS.map((k) => [k, p[k]]))),
      })),
  };
  return PREFIX + toBase64Url(JSON.stringify(state));
}

/**
 * Decodes a URL fragment against the open sources, matching tabs to sources by name.
 * Returns null without a view state, or the restored view and warnings about what could not be restored.
 * @param {string} hash
 * @param {Array<{id: number, name: string, datasets: Array<{name: string}>}>} sources Open sources.
 */
export function decodeView(hash, sources) {
  if (!hash.startsWith(PREFIX)) return null;
  let state;
  try {
    state = JSON.parse(fromBase64Url(hash.slice(PREFIX.length)));
  } catch {
    return { view: null, warnings: ["The view in the URL is not valid and was ignored."] };
  }
  if (state.v !== VERSION) return { view: null, warnings: ["The view in the URL is from another version and was ignored."] };

  const warnings = [];
  const byName = new Map(sources.map((s) => [s.name, s]));
  const tabs = [];
  for (const t of state.tabs ?? []) {
    const source = byName.get(t.source);
    if (!source) {
      warnings.push(`${t.source} of the URL view is not open, its tab was skipped. Open it with the + tab.`);
      continue;
    }
    const plots = [];
    for (const p of t.plots ?? []) {
      // Datasets are only known for parsed sources, so plots of sources still parsing are kept as they are. Plots
      // without a dataset, e.g. of a tab never shown, get one when shown.
      if (p.dataset != null && source.datasets.length && !source.datasets.some((d) => d.name === p.dataset)) {
        warnings.push(`Dataset ${p.dataset} is not in ${t.source}, its plot was skipped.`);
        continue;
      }
      plots.push({ ...p, kind: p.kind ?? "plot", splitValues: p.splitValues ?? [], filter: p.filter ?? "", columnFilter: p.columnFilter ?? "" });
    }
    tabs.push({ source: source.id, range: t.range ?? null, plots, eventCategories: t.events ?? null });
  }
  const active = byName.get(state.active)?.id ?? null;
  return { view: { timeMode: state.timeMode, active, tabs }, warnings };
}
