# Visualizer design

Browser-based visualizer for OCUDU artifacts (`ocudu-viz`). Living document: requirements and decisions are
updated as they are agreed.

## Scope

- Input: OCUDU artifacts parsed with the `parsers` package. Log metrics first, then other log content
  (procedures, errors), pcaps and traces.
- Output: interactive views in the browser, opened locally against one or more files.
- Separate package from `parsers`. `viz` depends on `parsers`, never the opposite.

## Data model

- **Source:** one input file (e.g. `du.log`, `cu.log`, a pcap). A view can hold several sources.
- **Dataset:** what a source type extracts from a source. Three kinds:
  - **Time series:** numeric fields over time, split by context (e.g. METRICS layers, trace latencies).
  - **Events:** timestamped points or intervals with a label (e.g. RRC procedures, errors, PRACH, handovers).
    Drawn as markers or spans over the plots.
  - **Records:** the raw entries behind the other datasets (e.g. log lines, packets), for drill-down.
- **Source type:** adapter from one artifact kind to datasets, built on `parsers`. Log metrics is the first
  source type. New artifact kinds add a source type, not changes to the views.

## Functional requirements

- **F1. Metric selection:** pick a dataset (e.g. METRICS layer `sched_ue`) and one or more of its fields.
- **F2. Split by context:** split a field into one series per context value (e.g. per `pci`, `ue`, `rnti`,
  `executor`).
- **F3. Filters:** boolean filter expressions over record fields (e.g. `pci == 1 and dl_mcs > 20`).
- **F4. Statistics:** min, max, mean and percentiles of the selected series over the visible range.
- **F5. Histogram view** of the selected field.
- **F6. Drill-down:** clicking a point or event shows the originating record and its neighbours.
- **F7. Units:** axes labelled with the dataset units (e.g. `MetricsParser.units`), auto-scaled for
  readability (e.g. us to ms).
- **F8. Time axis zoom and pan**, synchronized across all plots in a view.
- **F9. Multiple plots per view**, stacked with a shared time axis.
- **F10. Live tail:** follow a file that is still being written.
- **F11. Shareable state:** the current view (sources, datasets, fields, filters, time range) is encoded in
  the URL.
- **F12. Multiple sources:** `ocudu-viz cu.log du.log`. Every series and event is labelled with its source.
- **F13. Time modes:** absolute (shared wall clock, default) or relative (each source starts at t=0).
- **F14. Events overlay:** event datasets drawn on top of the time series plots.

## Non-functional requirements

- **N1. Data volume:** a single run can have ~1M metric records (e.g. 624k `sched_ue` lines from one
  multi-UE test). Interaction (zoom, pan, toggling series) must stay responsive at that size.
- **N2. Local first:** runs on a developer machine against local files, with one command and no manual
  build step.
- **N3. Offline:** no CDN or external services at runtime.
- **N4. Parsing stays in `parsers`:** the visualizer adds no artifact-format knowledge beyond mapping
  parser output to datasets.
- **N5. Container only for users:** running the visualizer needs only Docker (or Podman). Python, Node and
  all dependencies are inside the image. No third-party code is copied into the repository.
- **N6. Light runtime dependencies:** few, pure-pip Python packages. No pyarrow, pandas or system packages.

## Stack

| Layer          | Technology                                                       | Status   |
|----------------|------------------------------------------------------------------|----------|
| Backend        | FastAPI + uvicorn                                                | Decided  |
| Frontend       | Plain JS modules with JSDoc types, Vue 3, bundled by Vite        | Decided  |
| Charts         | uPlot                                                            | Decided  |
| Styling        | Plain CSS with custom properties                                 | Decided  |
| Record list    | Plain list of a window of records around the selection           | Decided  |
| Cache, queries | SQLite (Python standard library)                                 | Decided  |
| Packaging      | Docker image built locally by the `ocudu-viz` wrapper script     | Decided  |

Vue, uPlot and Vite come from npm, pinned in `frontend/package-lock.json`. The build writes the licenses of
the bundled packages to `THIRD-PARTY-LICENSES.txt`, served with the frontend.

## Decisions

### D1. Data transport

- JSON in columnar form (one array per column), e.g.
  `{"t": [...], "series": {"ue=1": [...]}, "record": [...]}`. Matches the uPlot data layout.
- Windows with up to ~50k points (to be tuned) are sent at full resolution.
- Larger windows are downsampled on the server to min/max per pixel bucket and series, so outliers stay
  visible. The browser sends its plot width.
- Zooming in fetches the new window at higher resolution.
- Every point carries the id of its record (e.g. log line number) for drill-down (F6).

### D2. Parse cache and query engine

- Each source is parsed once into a SQLite database: one table per dataset, one column per field, plus
  timestamp and record id. List values are stored as JSON text. Columns are added as fields appear.
- SQLite also serves the queries: filters (F3), splitting (F2), downsampling (D1) and statistics (F4).
- Filter expressions are translated from a small grammar (`field op value`, `and`, `or`, parentheses) into
  parameterized SQL, never passed through as SQL.
- Cache location: a per-user directory (mode 0700) under the system temp dir of the host (honours
  `$TMPDIR`), e.g. `/tmp/ocudu-viz-<uid>/`, mounted into the container at the same path. Cleared on reboot.
- Cache key: source path, size and mtime, plus the parser version. Stale caches are rebuilt.
- Size cap (default 2 GB), evicting the least recently used caches.
- Flags: `--cache-dir DIR` (persistent location), `--no-cache` (in-memory database), `--clear-cache`.
- Live tail (F10) appends rows to the source database.

### D3. Multiple sources

- Multiple sources per view from the first version (F12). Each source has its own cache database.
- Absolute time by default, relative time as an option (F13).
- The time range of a source spans its first to last log timestamp, widened by its dataset timestamps if
  needed, since log lines are not strictly time ordered. The default view is the union of the source
  ranges.
- Out of scope for the first version: automatic cross-source alignment (e.g. by RNTI or procedure), and
  source types not supported by `parsers` yet (e.g. UE logs).

### D4. First version scope

- In: CLI, log metrics source type, F1, F2, F6, F7, F8, F9, F12, F13, D1, D2.
- Deferred: F10 live tail, F14 events (needs an
  event parser in `parsers`), Docker.
- Without explicit split values, only the first 20 are returned, since sparse splits
  (e.g. ~1000 short-lived UEs) cannot be reduced by downsampling.

### D5. Layout and API

- Package `viz` (`ocudu-viz`): `cli.py`, `server.py`, `store.py`, `sources/` (one module per source type),
  `static/` (frontend build output, not in git).
- `frontend/`: the browser app sources (`src/`, `public/`), built by Vite into `viz/static/`.
- `Dockerfile` and the `ocudu-viz` wrapper script, see D12.
- `GET /api/sources`: sources with their datasets, fields (type, unit) and context fields.
- `GET /api/series?source&dataset&field&split_by&split_values&t0&t1&width`: one series per split value, each with its
  own timestamps, values and record ids. The browser aligns them with `uPlot.join`.
- `GET /api/context?source&dataset&field`: distinct values of a field, for split value selection.
- `GET /api/records?source&around&count`: raw records (log lines) around a record.
- Sources sharing a file name are labelled with the first directory where their paths differ.

### D6. Filters and statistics

- Filters (F3) use the grammar in `viz/filters.py`: comparisons (`== != < <= > >=`, `is [not] null`)
  joined by `and`, `or`, `not` and parentheses. Operands are numbers, strings, hex values, bare words or
  other fields. Values are in the canonical units of `parsers`.
- A filter applies to the series and the statistics of its plot.
- Statistics (F4) per series over the visible window: count, min, max, mean from SQL; p50, p95, p99 in
  Python, from an evenly spaced sample when the window has more than 2M points.

### D7. Histogram

- Per plot toggle between time series and histogram (F5). The histogram covers the visible window, with the
  plot filter and split applied, and is drawn as one stepped curve per split value over shared bins.
- 50 equal bins over the window's value range. Integer fields spanning at most 50 values get one bin per
  integer, centred on it.

### D8. Dataset labels and instances

- A source type can give a dataset a display label and an instance field, the context field naming the
  entity each row belongs to. METRICS layer `exec` is shown as `executors`, with instance field `executor`.
- Datasets with an instance field get a second selector listing its values, the first selected by default,
  plus `all`. The selection restricts the rows on the server, so it applies to series, statistics and
  histograms.

### D9. View state in the URL

- The view (F11) is encoded as base64url JSON in the URL fragment (`#v=...`), updated in place with
  `history.replaceState` shortly after each change, and restored on load.
- Saved: time mode, zoom range, and per plot its source, dataset, instance, field,
  split, selected split values, filter and view mode. The state carries a version number.
- Sources are saved by display name and remapped by name when opened with other files or another order.
  Plots of missing sources or datasets are skipped with a warning. No file paths are put in the URL.

### D10. Themes

- Light and dark themes, defined as CSS custom properties, including the series colors (`--s0` to `--s9`).
  The dark theme uses neutral charcoal surfaces, soft grey text, faint grid lines and a muted blue
  accent.
- A header selector chooses `auto` (follows the OS setting), `light` or `dark`. The preference is kept in
  browser storage and applied before the first paint. Charts are rebuilt on a theme change, without
  refetching data.

### D12. Container

- The image (`ocudu-viz:latest`) is built locally from the `tools/` directory, by the `ocudu-viz` wrapper on
  every run, so that source changes are picked up; unchanged sources hit the build cache. A Node stage
  builds the frontend; a Python stage installs `parsers` and `viz` with the built frontend and runs the
  server. Users need no Python environment or Node.
- The wrapper mounts the home directory read-only at the same path, plus the directory of any file outside
  it and any `--root DIR`, so files and links keep their host paths. This also prepares selecting files from
  the page later, limited to the mounted roots.
- The container runs as the host user, so that it can read the user's files and owns the cache it writes.
- The server listens on all interfaces inside the container, and the port is published on the host
  loopback only (`127.0.0.1`), never on other interfaces.
- The wrapper opens the browser once the server listens, since a container cannot open the host browser.

## Open questions

None yet.
