# ocudu-viz

Browser-based visualizer for OCUDU artifacts. See [DESIGN.md](DESIGN.md) for requirements and decisions.

## Requirements

Docker (or Podman, see below). Nothing else: the image contains Python, the parsers and the built frontend.

## Usage

Run the `ocudu-viz` script in this directory, or put it on your `PATH` (e.g. a symlink in `~/.local/bin`):

```bash
tools/viz/ocudu-viz gnb.log                  # one source
tools/viz/ocudu-viz du1/du.log du2/du.log    # several sources, on one time axis
```

The script builds the `ocudu-viz:latest` image when needed (cached after the first build), then runs it:

- Your home directory is mounted read-only at the same path, so files keep their host paths. Files outside
  it get their directory mounted too; use `--root DIR` to mount more directories, e.g. shared artifacts.
- The server is published on `127.0.0.1` only, on port 8765 or the next free one, and the browser opens on
  it once the files are parsed.
- The first open of a file parses it into a cache under `/tmp/ocudu-viz-<uid>/` on the host, which makes
  later opens instant.

In the page:

- Pick source, dataset (METRICS layer), field and optionally a context field to group by (e.g. `ue`).
  Without a group selection, the first 20 groups are shown.
- Drag or use the wheel to zoom, Shift+drag to pan, double-click to reset. All plots share the time axis.
- Click a point to see its log line and the lines around it.
- Time mode `relative` starts each source at t=0.

Large windows are downsampled to min/max per pixel, so spikes stay visible. Zoom in for full resolution.

## Options

| Option            | Description                                                                 |
|-------------------|-----------------------------------------------------------------------------|
| `--port N`        | Host port to serve on, or the next free one (default 8765).                 |
| `--root DIR`      | Also mount DIR read-only. Repeatable. The home directory is always mounted. |
| `--no-browser`    | Do not open the browser.                                                    |
| `--rebuild`       | Rebuild the image from scratch, without the build cache.                    |
| `--cache-size GB` | Cache size limit, least recently used caches are removed first (default 2). |
| `--no-cache`      | Keep parsed data in memory only.                                            |
| `--clear-cache`   | Remove all caches before starting.                                          |

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
