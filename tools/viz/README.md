# ocudu-viz

Browser-based visualizer for OCUDU artifacts. See [DESIGN.md](DESIGN.md) for requirements and decisions.

## Requirements

Docker (or Podman, see below). Nothing else: the image contains Python, the parsers and the built frontend.

## Usage

Run the `ocudu-viz` script in this directory, or put it on your `PATH` (e.g. a symlink in `~/.local/bin`):

```bash
tools/viz/ocudu-viz                          # no files, open them from the page
tools/viz/ocudu-viz gnb.log                  # one source
tools/viz/ocudu-viz du1/du.log du2/du.log    # several sources, one tab each
```

The `+` tab in the page browses the mounted directories (your home, the temp dir and any `--root`) and
opens the chosen file in a new tab. Its `Recent` view lists the last files opened in this browser, newest
first, for one-click reopening. Each open file has its own tab, with its own plots and zoom; close a file
with the `✕` of its tab.
Large logs are parsed in the background, with the progress shown on the file, and the page stays usable
meanwhile. Opened files stay open for as long as the server runs, also across page reloads.

The script builds the `ocudu-viz:latest` image when needed (cached after the first build), then runs it:

- Your home directory and the temp dir (`$TMPDIR` or `/tmp`, where gnb logs often end up) are mounted
  read-only at the same path, so files keep their host paths. Files outside them get their directory
  mounted too; use `--root DIR` to mount more directories, e.g. shared artifacts.
- The server is published on `127.0.0.1` only, on port 8765 or the next free one, and the browser opens on
  it once the files are parsed.
- The first open of a file parses it into a cache under `/tmp/ocudu-viz-<uid>/` on the host, which makes
  later opens instant.

In the page:

- Datasets whose rows belong to named entities get a second selector next to the dataset, e.g.
  `executors` lists the executors (`cu_cp_exec`, `mac_cell_exec#0`, ...). `all` selects every entity, which
  combines with split by to compare them.
- Pick source, dataset (METRICS layer), field and optionally a context field to split by, giving one
  series per value (e.g. one per `ue`). Without a selection of values, the first 20 are shown.
- Drag or use the wheel to zoom, Shift+drag to pan, double-click to reset. The plots of a tab share the time
  axis.
  `reset zoom` shows the whole time range of the logs, `fit metrics` the time range of the plotted metrics.
- The `events` chips above the plots show event markers on the time plots, per category (random access, UE
  lifecycle, RRC, mobility, failures, warnings and errors), with their count in the file. All start hidden.
  Hover a marker to see its event, click it to see its log line.
- Click a point to see its log line and the lines around it. Drag the top edge of the log pane to resize it,
  double-click it to reset the height.
- The top-right corner of a plot shows the time and value under the mouse. The legend below shows the
  nearest data point.
- Filter the rows of a plot with an expression, applied on Enter. Values are in the base units of the
  parser (us, bps):

  ```text
  dl_mcs > 20 and pci == 1
  rnti == 0x4601 or (ta is not null and ta > 1.5)
  dl_mcs > ul_mcs
  ```

  Operators: `== != < <= > >=`, `is null`, `is not null`, combined with `and`, `or`, `not` and parentheses.
  Strings can be quoted or bare (`type == ue_create`). A bare word naming a field compares two fields.
- Switch a plot from `time series` to `histogram` to see the value distribution of the visible window,
  one curve per split value. Integer fields with few values (e.g. MCS) get one bin per value.
- `+ plot` and `+ table` below the panels of a tab add a plot or a table. A table shows all the metrics of
  a layer for the visible window at full resolution, one row per metrics line. Type words in its column box
  to show only the metric columns whose name contains any of them (e.g. `latency brate`), and use the row
  filter like in plots. Click a row to see its log line. `export CSV` downloads all rows of the visible
  window with the shown columns, values in the canonical unit.
- Below each plot, a table shows count, min, mean, p50, p95, p99 and max of each series in the visible
  window, with the plot filter applied. Percentiles are sampled for windows over 2M points.
- Time mode `relative` shows the time since the start of the log.

The current view (plots, splits, filters, zoom and time mode) is kept in the page URL, so a reload
restores it and a bookmark or shared link reopens it, as long as `ocudu-viz` runs with the same files.
Sources are matched by name; plots of sources that are not open are skipped with a warning.

The `theme` selector in the header switches between light and dark, or follows the
operating system with `auto`. The choice is remembered by the browser.

Large windows are downsampled to min/max per pixel, so spikes stay visible. Zoom in for full resolution.

## Options

| Option            | Description                                                                 |
|-------------------|-----------------------------------------------------------------------------|
| `--port N`        | Host port to serve on, or the next free one (default 8765).                 |
| `--root DIR`      | Also mount DIR read-only and open its files from the page. Repeatable.     |
| `--no-browser`    | Do not open the browser.                                                    |
| `--rebuild`       | Rebuild the image from scratch, without the build cache.                    |
| `--cache-size GB` | Cache size limit, least recently used caches are removed first (default 2). |
| `--no-cache`      | Keep parsed data in memory only.                                            |
| `--clear-cache`   | Remove all caches before starting.                                          |
| `--clean`         | Remove the ocudu-viz images and parse caches, then exit.                    |

Set `OCUDU_VIZ_DOCKER=podman` to use Podman instead of Docker.

## Development

- `viz/`: Python package (FastAPI server, SQLite store, CLI run inside the container).
- `frontend/`: browser app, plain JavaScript modules with Vue and uPlot from npm, bundled by Vite into
  `viz/static/` (not in git). `THIRD-PARTY-LICENSES.txt` in the build lists the licenses of the bundled
  packages.
- `Dockerfile`: a Node stage builds the frontend, a Python stage installs the packages and serves it.

Python tests need no Node:

```bash
pip install -e tools/parsers -e "tools/viz[test]"
python3 -m unittest discover -s tools/viz/tests -t tools/viz
```

Frontend work outside the container needs Node 22:

```bash
cd tools/viz/frontend
npm ci
npm run build     # writes viz/static, served by a local "ocudu-viz FILE" from the Python package
npm run dev       # live-reloading dev server, proxying /api to an ocudu-viz server on port 8765
```
