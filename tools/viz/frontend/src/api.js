// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

/**
 * GETs a JSON API endpoint. Array parameters are sent as repeated keys.
 * @param {string} path
 * @param {Record<string, any>} [params]
 * @param {AbortSignal} [signal]
 */
export async function getJSON(path, params = {}, signal) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined) continue;
    for (const v of Array.isArray(value) ? value : [value]) query.append(key, String(v));
  }
  const res = await fetch(`${path}?${query}`, { signal });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}
