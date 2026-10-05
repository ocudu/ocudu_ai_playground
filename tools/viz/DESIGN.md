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
  - **Time series:** numeric fields over time, grouped by context (e.g. METRICS layers, trace latencies).
  - **Events:** timestamped points or intervals with a label (e.g. RRC procedures, errors, PRACH, handovers).
    Drawn as markers or spans over the plots.
  - **Records:** the raw entries behind the other datasets (e.g. log lines, packets), for drill-down.
- **Source type:** adapter from one artifact kind to datasets, built on `parsers`. Log metrics is the first
  source type. New artifact kinds add a source type, not changes to the views.

## Functional requirements

- **F1. Metric selection:** pick a dataset (e.g. METRICS layer `sched_ue`) and one or more of its fields.
- **F2. Group by context:** split a field into one series per context value (e.g. per `pci`, `ue`, `rnti`,
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
| Backend        | FastAPI + uvicorn                                                | Proposed |
| Frontend       | Plain JS modules with JSDoc types, Vue 3, bundled by Vite        | Proposed |
| Charts         | uPlot                                                            | Proposed |
| Styling        | Plain CSS with custom properties                                 | Proposed |
| Record list    | Own minimal virtual list                                         | Proposed |
| Cache, queries | SQLite (Python standard library)                                 | Proposed |
| Packaging      | Docker image built locally by the `ocudu-viz` wrapper script     | Proposed |

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
- SQLite also serves the queries: filters (F3), grouping (F2), downsampling (D1) and statistics (F4).
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
- Out of scope for the first version: automatic cross-source alignment (e.g. by RNTI or procedure), and
  source types not supported by `parsers` yet (e.g. UE logs).

## Open questions

None yet.
