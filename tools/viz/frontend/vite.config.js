// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  // Relative asset URLs, so the build works wherever the server mounts it.
  base: "./",
  resolve: {
    // Components use template strings, which need the build of Vue that includes the template compiler.
    alias: { vue: "vue/dist/vue.esm-bundler.js" },
  },
  define: {
    __VUE_OPTIONS_API__: "true",
    __VUE_PROD_DEVTOOLS__: "false",
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: "false",
  },
  build: {
    outDir: fileURLToPath(new URL("../viz/static", import.meta.url)),
    emptyOutDir: true,
  },
  server: {
    // During frontend development, API calls go to an ocudu-viz server on its default port.
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
