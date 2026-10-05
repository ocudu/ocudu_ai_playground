// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

// Writes the licenses of the runtime dependencies, and theirs, to THIRD-PARTY-LICENSES.txt in the build output.

import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outFile = join(root, "..", "viz", "static", "THIRD-PARTY-LICENSES.txt");

/** @param {string} name */
function readPackage(name) {
  const dir = join(root, "node_modules", name);
  return { dir, pkg: JSON.parse(readFileSync(join(dir, "package.json"), "utf8")) };
}

/** @param {string} dir */
function licenseText(dir) {
  const file = readdirSync(dir).find((f) => /^(licen[sc]e|copying)(\.|$)/i.test(f));
  return file ? readFileSync(join(dir, file), "utf8").trim() : "";
}

const rootPkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const seen = new Map();
const pending = Object.keys(rootPkg.dependencies ?? {});
while (pending.length) {
  const name = pending.pop();
  if (seen.has(name) || !existsSync(join(root, "node_modules", name))) continue;
  const { dir, pkg } = readPackage(name);
  seen.set(name, { version: pkg.version, license: pkg.license, text: licenseText(dir) });
  pending.push(...Object.keys(pkg.dependencies ?? {}));
}

const sections = [...seen.entries()]
  .sort(([a], [b]) => a.localeCompare(b))
  .map(([name, p]) => `${name} ${p.version} (${p.license})\n\n${p.text || "No license file found in the package."}`);
writeFileSync(outFile, `Licenses of the third-party packages the ocudu-viz frontend is built from (the bundle may include only parts of them).\n\n${sections.join("\n\n" + "-".repeat(78) + "\n\n")}\n`);
console.log(`Wrote the licenses of ${seen.size} packages to ${outFile}`);
