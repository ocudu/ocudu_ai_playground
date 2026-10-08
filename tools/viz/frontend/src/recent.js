// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

// Recently opened files and directories, kept in browser storage, newest first.

// Browser storage key of the recent files.
const STORAGE_KEY = "ocudu-viz-recent";
const MAX_RECENT = 15;

/** @returns {Array<{path: string, openedAt: number, dir?: boolean}>} */
export function loadRecent() {
  try {
    const list = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(list) ? list.filter((e) => e && typeof e.path === "string") : [];
  } catch {
    // Storage can be unavailable, e.g. in private windows, or hold invalid data.
    return [];
  }
}

/** @param {Array<{path: string, openedAt: number, dir?: boolean}>} list */
function save(list) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_RECENT)));
  } catch {
    // Storage can be unavailable, e.g. in private windows.
  }
}

/**
 * Moves a path to the top of the recent files.
 * @param {string} path
 * @param {boolean} [dir] Whether the path is a directory.
 */
export function addRecent(path, dir = false) {
  save([{ path, openedAt: Date.now(), dir }, ...loadRecent().filter((e) => e.path !== path)]);
}

/** @param {string} path */
export function removeRecent(path) {
  save(loadRecent().filter((e) => e.path !== path));
}

export function clearRecent() {
  save([]);
}
