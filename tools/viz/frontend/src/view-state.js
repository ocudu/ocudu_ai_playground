// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

// Bumped when the encoded state changes incompatibly.
const VERSION = 3;
const PREFIX = "#v=";
// Plot properties saved in the view state, besides the file of its source.
const PLOT_KEYS = ["kind", "dataset", "instance", "field", "splitBy", "splitValues", "filter", "mode", "columnFilter", "joined", "groupBy"];

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
 * Runs are identified by name and sources by file name, not path.
 * @param {{runs: Array<{id: number, name: string}>, sources: Array<{file: string}>, tabs: Record<number, any>, activeId: number | null, timeMode: string}} app
 */
export function encodeView(app) {
  const state = {
    v: VERSION,
    timeMode: app.timeMode,
    active: app.runs.find((r) => r.id === app.activeId)?.name ?? null,
    tabs: app.runs
      .filter((r) => app.tabs[r.id])
      .map((r) => ({
        run: r.name,
        range: app.tabs[r.id].userRange,
        events: app.tabs[r.id].eventCategories,
        alone: app.tabs[r.id].relatedAnswered || undefined,
        plots: app.tabs[r.id].plots.map((p) => ({
          source: app.sources[p.source]?.file ?? null,
          ...Object.fromEntries(PLOT_KEYS.map((k) => [k, p[k]])),
        })),
      })),
  };
  return PREFIX + toBase64Url(JSON.stringify(state));
}

/**
 * Decodes a URL fragment against the open runs, matching tabs to runs by name and plots to sources by file name.
 * Returns null without a view state, or the restored view and warnings about what could not be restored.
 * @param {string} hash
 * @param {Array<{id: number, name: string, sources: number[]}>} runs Open runs.
 * @param {Array<{id: number, file: string, datasets: Array<{name: string}>}>} sources Sources by id.
 */
export function decodeView(hash, runs, sources) {
  if (!hash.startsWith(PREFIX)) return null;
  let state;
  try {
    state = JSON.parse(fromBase64Url(hash.slice(PREFIX.length)));
  } catch {
    return { view: null, warnings: ["The view in the URL is not valid and was ignored."] };
  }
  if (state.v !== VERSION) return { view: null, warnings: ["The view in the URL is from another version and was ignored."] };

  const warnings = [];
  const byName = new Map(runs.map((r) => [r.name, r]));
  const tabs = [];
  for (const t of state.tabs ?? []) {
    const run = byName.get(t.run);
    if (!run) {
      warnings.push(`${t.run} of the URL view is not open, its tab was skipped. Open it with the + tab.`);
      continue;
    }
    const byFile = new Map(run.sources.map((id) => [sources[id]?.file, sources[id]]));
    const plots = [];
    for (const p of t.plots ?? []) {
      const source = byFile.get(p.source);
      if (!source) {
        warnings.push(`${p.source} is not in ${t.run}, its plot was skipped.`);
        continue;
      }
      // Datasets are only known for parsed sources, so plots of sources still parsing are kept as they are. Plots
      // without a dataset, e.g. of a tab never shown, get one when shown.
      if (p.dataset != null && source.datasets.length && !source.datasets.some((d) => d.name === p.dataset)) {
        warnings.push(`Dataset ${p.dataset} is not in ${p.source}, its plot was skipped.`);
        continue;
      }
      plots.push({
        ...p,
        source: source.id,
        kind: p.kind ?? "plot",
        splitValues: p.splitValues ?? [],
        filter: p.filter ?? "",
        columnFilter: p.columnFilter ?? "",
      });
    }
    tabs.push({ run: run.id, range: t.range ?? null, plots, eventCategories: t.events ?? null, relatedAnswered: Boolean(t.alone) });
  }
  const active = byName.get(state.active)?.id ?? null;
  return { view: { timeMode: state.timeMode, active, tabs }, warnings };
}
