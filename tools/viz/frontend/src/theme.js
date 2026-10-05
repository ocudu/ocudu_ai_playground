// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

// Browser storage key of the theme preference.
const STORAGE_KEY = "ocudu-viz-theme";
const PREFERENCES = ["auto", "light", "dark"];
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

/** @returns {"auto" | "light" | "dark"} */
export function loadThemePreference() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (PREFERENCES.includes(stored)) return stored;
  } catch {
    // Storage can be unavailable, e.g. in private windows.
  }
  return "auto";
}

/** @param {"auto" | "light" | "dark"} preference */
export function saveThemePreference(preference) {
  try {
    localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Storage can be unavailable, e.g. in private windows.
  }
}

/**
 * Applies a theme preference to the page, resolving "auto" from the OS setting.
 * @param {"auto" | "light" | "dark"} preference
 */
export function applyTheme(preference) {
  const dark = preference === "dark" || (preference === "auto" && darkQuery.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

/**
 * Calls back when the OS color scheme changes.
 * @param {() => void} callback
 */
export function onSystemThemeChange(callback) {
  darkQuery.addEventListener("change", callback);
}
