// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

// Bumped when the encoded state changes incompatibly.
const VERSION = 1;
const PREFIX = "#v=";
// Plot properties saved in the view state.
const PLOT_KEYS = ["source", "dataset", "instance", "field", "splitBy", "splitValues", "filter", "mode"];

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
 * Encodes the view as a URL fragment. Sources are identified by name, not path.
 * @param {{sources: Array<{name: string}>, plots: Array<Record<string, any>>, timeMode: string, userRange: {min: number, max: number} | null}} view
 */
export function encodeView(view) {
  const state = {
    v: VERSION,
    sources: view.sources.map((s) => s.name),
    timeMode: view.timeMode,
    range: view.userRange,
    plots: view.plots.map((p) => Object.fromEntries(PLOT_KEYS.map((k) => [k, p[k]]))),
  };
  return PREFIX + toBase64Url(JSON.stringify(state));
}

/**
 * Decodes a URL fragment against the open sources, remapping source indexes by name.
 * Returns null without a view state, or the restored view and warnings about what could not be restored.
 * @param {string} hash
 * @param {Array<{name: string, datasets: Array<{name: string}>}>} sources
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
  const names = sources.map((s) => s.name);
  // Index of each saved source among the open ones, or -1.
  const mapping = state.sources.map((name, i) => (names[i] === name ? i : names.indexOf(name)));
  state.sources.forEach((name, i) => {
    if (mapping[i] < 0) warnings.push(`Source ${name} of the URL view is not open, its plots were skipped.`);
  });

  const plots = [];
  for (const p of state.plots) {
    const source = mapping[p.source] ?? -1;
    if (source < 0) continue;
    if (!sources[source].datasets.some((d) => d.name === p.dataset)) {
      warnings.push(`Dataset ${p.dataset} is not in ${names[source]}, its plot was skipped.`);
      continue;
    }
    plots.push({ ...p, source, splitValues: p.splitValues ?? [], filter: p.filter ?? "" });
  }
  return { view: { timeMode: state.timeMode, range: state.range, plots }, warnings };
}
