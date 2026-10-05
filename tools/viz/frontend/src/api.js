// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

/**
 * Builds a query string, skipping null values and sending array values as repeated keys.
 * @param {Record<string, any>} params
 */
export function buildQuery(params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined) continue;
    for (const v of Array.isArray(value) ? value : [value]) query.append(key, String(v));
  }
  return query.toString();
}

/**
 * GETs a JSON API endpoint.
 * @param {string} path
 * @param {Record<string, any>} [params]
 * @param {AbortSignal} [signal]
 */
export async function getJSON(path, params = {}, signal) {
  return handleResponse(await fetch(`${path}?${buildQuery(params)}`, { signal }));
}

/**
 * POSTs a JSON body to an API endpoint.
 * @param {string} path
 * @param {any} body
 */
export async function postJSON(path, body) {
  return handleResponse(
    await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  );
}

/** @param {Response} res */
async function handleResponse(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}
