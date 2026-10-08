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
- **Run:** the sources shown together in one tab, on one time axis: the gNB artifacts of one directory, or a single
  file (D16).
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
- **F12. Multiple sources:** `ocudu-viz cu.log du.log`. Each source is shown in its own tab, with its own
  plots and zoom range; one tab is shown at a time.
- **F13. Time modes:** absolute (log wall clock, default) or relative (time since the start of the log).
- **F14. Events overlay:** event datasets drawn on top of the time series plots.
- **F15. Open files from the page:** start without files and open them from a file browser in the page.
- **F16. Table widgets and CSV export:** all the metrics of a dataset as a table, exportable as CSV.

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

- Multiple sources from the first version (F12). Each source has its own cache database.
- Each run has its own tab, with its plots, zoom range and drill-down (D16). Only the selected tab is shown, so
  runs are not compared side by side.
- Absolute time by default, relative time as an option (F13).
- The time range of a source spans its first to last log timestamp, widened by its dataset timestamps if
  needed, since log lines are not strictly time ordered. It is the default view of its tab.
- Out of scope for the first version: automatic cross-source alignment (e.g. by RNTI or procedure), and
  source types not supported by `parsers` yet (e.g. UE logs).

### D4. First version scope

- In: CLI, log metrics source type, F1, F2, F6, F7, F8, F9, F12, F13, D1, D2.
- Deferred: F10 live tail, F14 events, Docker.
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
- Saved: time mode, the selected tab, and per tab its source, zoom range and plots, each with its dataset,
  instance, field, split, selected split values, filter and view mode. The state carries a version number.
- Tabs are saved by source display name and matched by name to the open sources. Tabs of sources that are
  not open, and plots of missing datasets, are skipped with a warning. No file paths are put in the URL.

### D10. Themes

- Light and dark themes, defined as CSS custom properties, including the series colors (`--s0` to `--s9`).
  The dark theme uses neutral charcoal surfaces, soft grey text, faint grid lines and a muted blue
  accent.
- A header selector chooses `auto` (follows the OS setting), `light` or `dark`. The preference is kept in
  browser storage and applied before the first paint. Charts are rebuilt on a theme change, without
  refetching data.

### D11. Table widgets and CSV export

- Below the panels of a tab, `+ plot` adds a plot and `+ table` a table widget. A table shows a whole
  dataset of the tab's file: dataset and instance are selected, not a field. Its rows are the dataset rows of the visible window at full
  resolution, with the row filter applied: time, record id (log line), context fields, then all other fields.
- A column filter, applied as it is typed, shows the metric columns whose name contains any of its words.
  Context columns stay shown. Numeric columns are scaled to a display unit from the loaded rows.
- The page shows the first 1000 rows (`GET /api/table`). `GET /api/table.csv` streams all rows of the
  window with the shown columns, values in the canonical unit named in the column header (e.g.
  `dl_brate_bps`, `cpu_load_pct`), times in ISO 8601 UTC.
- Table widgets are saved in the URL view state with the plots of their tab.

### D12. Container

- The image (`ocudu-viz:latest`) is built locally from the `tools/` directory, by the `ocudu-viz` wrapper on
  every run, so that source changes are picked up; unchanged sources hit the build cache. A Node stage
  builds the frontend; a Python stage installs `parsers` and `viz` with the built frontend and runs the
  server. Users need no Python environment or Node.
- The wrapper mounts the home and temp (`$TMPDIR` or `/tmp`) directories read-only at the same path, plus
  the directory of any file outside them and any `--root DIR`, so files and links keep their host paths.
  The temp dir is included because gnb logs are often written there. The parse cache, under the temp dir,
  is mounted writable on top.
- The container runs as the host user, so that it can read the user's files and owns the cache it writes.
- The server listens on all interfaces inside the container, and the port is published on the host
  loopback only (`127.0.0.1`), never on other interfaces.
- The wrapper opens the browser once the server listens, since a container cannot open the host browser.
- The image carries the label `org.ocudu.tool=ocudu-viz`. After each build the wrapper prunes the untagged
  images with that label, which rebuilds leave behind, and `--clean` removes all of them with the parse
  cache. Containers run with `--rm` and no Docker volumes are created.

### D13. Opening files from the page

- The server only lists and opens files under allowed roots: the directories given with `--root`, the
  home and temp directories by default. The wrapper passes the directories it mounts. Paths are resolved, following
  symlinks, before checking them against the roots.
- `GET /api/roots` and `GET /api/fs?path&hidden` list directories. `POST /api/sources {path}` opens a file:
  parsing runs in a background thread, and `/api/sources` reports each source's status (`parsing`, `ready`,
  `error`, `closed`) and progress, which the page polls while a source is parsing. Opening an open file
  selects its tab. `DELETE /api/sources/{id}` closes a source and releases its store; ids are not reused.
- Opened sources stay in the server for as long as it runs, so reloads keep them. The URL view state still
  contains no file paths.
- The file dialog has a `Recent` view with the last 15 files opened, kept in browser storage, so that it
  survives server restarts and reboots without a writable location outside the container. A recent file
  that fails to open is dropped from the list.

### D14. Events overlay

- Events are recognized by `parsers.log.events` in a second pass over the log, after the datasets are served, so that
  plots do not wait for them: on large logs, recognizing events takes longer than parsing the metrics. They are stored
  in their own cache file, built aside and renamed when complete, with their time, record, type, category, logger,
  level, UE, RNTI, cause and text. Source types without events skip the pass.
- `/api/sources` reports the state of the events of each source (`pending`, `parsing`, `ready`, `error`) and their
  count per category, and `GET /api/events?source&t0&t1&categories&ue&limit`
  returns the events of a window, capped at 5000.
- Events are dashed vertical lines over the time plots of the tab, coloured by category. Hovering one shows its text,
  clicking it opens its log line.
- The time plots mark only the log events that matter next to metrics, each with a chip and its count in the logs of
  the tab: `RACH` (PRACH detections), `RLF`, `warnings` and `errors`, disabled at 0 so that a clean log reads as one.
  `/api/events` selects events by category and by type. All start hidden, and the shown ones are kept in the URL view
  state. The trace shows all the events of all the categories.
- The `+ trace` widget shows the events per UE on the time axis of the tab: one bar per UE context, from its random
  access or creation to its deletion, with a glyph per event, and a last row, `common`, with the events of no UE. Each UE has its own
  row, labelled with its DU UE index and RNTI, in start order. The trace shows 25 UE rows at a time and scrolls over the
  others with its own scrollbar, keeping the time axis and the row of events of no UE in view. Events are assigned to UE contexts by `parsers.log.events.UeTracker` while they are parsed: by
  RNTI, by DU UE index, and for CU-CP events by the RNTI of the RRC messages of their CU-CP UE index.
  `GET /api/trace?source&t0&t1&max_lanes&limit` returns the UE contexts active in a window and its events.
- The trace has a filter like the plots (D6), over the event fields type, category, layer, level, ue, rnti, cause and
  text, evaluated by SQLite over the events of the window, with the UE index and RNTI of their lane for events
  without them. It keeps the matching events and the lanes they are in, and applies to joined traces too.
- Most UE events are info lines, so logs whose layers log below info lack them. The log levels come from the
  configuration echo at the top of the log (`parsers.log.config`), and `/api/sources` reports a note naming the quiet
  layers and the events they hide, shown in the event bar and the trace.

### D15. Parallel parsing

- Most of the parse time of a metrics-heavy log goes to parsing the METRICS lines in Python, not to finding them, so
  the metrics of large logs are parsed in chunks by a pool of worker processes.
- The pool is shared by all sources for as long as the server runs, and started in the background when the server
  starts, so that the first large log does not wait for it. `-j K` sets its workers, 1 for no pool; by default there
  is one per CPU the process may use, up to 12: on a 16-core machine, a metrics-heavy log parses no faster with more. Workers start from a fork server, since forking the multithreaded server could deadlock. A pool whose
  worker dies is replaced, and its chunks are parsed in the server process.
- Chunks are byte ranges, about 4 per worker and at least 4 MB, so that logs under 8 MB, which parse as fast either
  way, stay in the server process, whose starts are moved to the next line that begins a
  log entry, so that multi-line entries stay whole. The chunking comes from `parsers.log.chunks`, which other tools use
  through `MetricsParser.parse_file()`; viz keeps the pool and its own workers, which return rows ready to store. Workers read their range from the file and return rows grouped by
  layer and grouped by field names, with values ready to store, the column types of each field and their units. Workers
  first count the lines of each chunk, so that they then number lines as in the whole file: line numbers are the
  record ids that link plots, tables and events to the log pane.
- The server process takes the results in file order, merges the units as a single pass would, and inserts each
  group of rows at once while later chunks are still parsed, leaving it mostly waiting for the workers. The cache has
  the same contents as with a single pass.

### D16. Runs

- A tab shows a run: one or more sources on one time axis. A run is either a single file, opened on its own, or the
  gNB artifacts of one directory: the gNB, DU or CU logs and the `mac`, `rlc`, `f1ap`, `e1ap` and `ngap` pcaps, and
  later `metrics.json`. Files of other nodes (5GC, UE simulator) and of other directories are not part of a run.
- Opening a directory, from the command line, opens a run with the supported files in it. Opening a file opens a run
  of that file, since files in e.g. `~/Downloads` or `/tmp` are often unrelated to each other. When other files of its
  directory were written by the same run, its tab asks whether to open them too, which makes it the run of the
  directory. The question is a dialog, shown as soon as the file is opened, and its answer is kept in the URL view
  state. Files are of the same run by content, not name, since names get edited: logs whose first line names the
  same build (`Built in <mode> mode using commit <hash> on branch <branch>`) and whose time spans overlap
  (`parsers.log.run`), and pcaps whose time spans, from the times in their packet headers, overlap. Overlaps allow
  60 s of slack. A run can add or remove files of its directory from its tab.
- Each source keeps its own parse, cache database, status and id. A run lists its sources, and the page polls them as
  today.
- Plots name their source: the dataset picker groups datasets by source, e.g. `du.log › sched_ue`, so one tab can
  plot metrics of several sources. The URL view state lists the files of each run.
- Events and the trace merge the events of all the sources of a run. Pcaps give the protocol messages, i.e. F1AP,
  NGAP and E1AP messages, the RRC and NAS messages that F1AP carries, and failures, independently of log levels and
  log wording. Logs give what pcaps do not show, e.g. PRACH, contention resolution timeouts, RLF, warnings and errors.
  Logs and F1AP pcaps both show RRC messages, so a trace of the F1AP pcap with the events of the logs leaves out the RRC
  events of the logs. Linking a packet to the log line of the same message is open.
- UE contexts are joined across the sources of a run, since pcaps identify UEs more reliably than logs: a log can
  create a UE without its RNTI, e.g. the target of a handover, and log the RNTI of its later events only. The trace
  of an F1AP pcap joins the UE lanes of the logs of its run (`/api/runs/{id}/trace`, `+ log events`): a log lane with
  an RNTI joins the F1AP UE context with that C-RNTI whose lifetime, with 2 s of slack, overlaps it, and a log lane
  without one joins the context starting nearest its creation, within 1 s, i.e. its InitialULRRCMessageTransfer or
  UEContextSetup. Log lanes of no context keep their own row. A trace of a log of a run with an F1AP pcap also shows
  its events on these UE contexts, the ones it has events in. RNTIs are compared as logs print them
  (`parsers.ran.rnti`). The F1AP gNB-DU-UE-F1AP-ID is not the DU UE index of the logs, so they are not compared. A
  trace row shows the DU UE index, RNTI and protocol identifiers of its UE. Joining NGAP and E1AP contexts, which
  carry no RNTI, is open.
- Drill-down follows the source of the clicked item: log lines for logs, and the frame and its one-line tshark summary
  for pcaps, with the decoded frame on demand (D17).
- Sources of one run share the gNB clock, so they have no time offset.
- Steps: runs of several log sources; a pcap source type on `parsers.pcap`, with its events in the trace; the UE join
  and UE filter. The container image adds `tshark`.

### D17. Pcap sources

- `PcapSource` reads NGAP, F1AP, E1AP, MAC-NR and RLC-NR pcaps through `parsers.pcap`, which runs `tshark`. The
  protocol comes from the dissector of the first frame, not the file name. A pcap is read in one pass over its frames
  with the fields of its protocol only (`capture.read()`), since dissection takes the time and each field adds to it,
  and the events are built from the same pass. Without `tshark` on the `PATH`, pcaps are
  not supported files.
- Records are frames, identified by frame number, with their tshark summary (time, protocols, info) as text, stored in
  the cache. The record pane shows the decoded frame beside the frames (`/api/records/detail`), decoded on demand,
  with the 3GPP layers in full.
- Datasets: `messages` for NGAP, F1AP and E1AP, one row per message with its procedure, outcome, UE identifiers,
  cause, tshark summary and size, plus the RRC and NAS messages and C-RNTI for F1AP; `pdus` for MAC and RLC, one row
  per PDU with its size, direction and UE identifiers.
- Events: one per NGAP, F1AP or E1AP message, in category `rrc` for F1AP messages carrying RRC, `failure` for
  unsuccessful outcomes, else `ngap`, `f1ap` or `e1ap`. Each UE context is a trace lane, from the first message with
  its identifiers until the response that releases it (UEContextRelease for NGAP and F1AP, bearerContextRelease for
  E1AP), since later UEs reuse the identifiers. Lanes are labelled with their identifiers, and F1AP lanes with their
  C-RNTI in hex, as logs print it. MAC and RLC pcaps have no events.
- tshark reads pcaps through a link or copy under the cache directory only when it cannot read them in place, e.g.
  under the AppArmor profile of tshark on Ubuntu. `--clear-cache` removes them. The container image installs
  `tshark`.

## Open questions

None yet.
