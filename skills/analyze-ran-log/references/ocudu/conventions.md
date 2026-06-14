# ocudu conventions

Type-specific deltas for `ocudu` artifacts (OCUDU `gnb`/`du`/`cu`/`cu_cp`/
`cu_up` binaries). The shared resolve / efficiency / memory flow lives in the
skill `SKILL.md`; this file carries only what is particular to OCUDU gNB logs.

A single run directory typically contains:

| File | Description |
|---|---|
| `gnb.log` | Per-layer protocol trace (CONFIG echo + RRC/NGAP/F1AP/E1AP/MAC/PHY/SCHED/PDCP/GTPU/...) |
| `stdout.log` | Console: banner, cell config, AMF connection, metrics table, shutdown lines |
| `ocudu_gnb.yml` | YAML config the binary was started with (multi-document — sections are concatenated) |
| `metrics.json` | Per-period JSON metrics (one object per record, NDJSON-like) |
| `ps_info_gnb.txt` | Process CPU/memory snapshot (rarely needed) |
| `*.pcap` | Optional protocol captures — analyze with the `pcap` type (`references/pcap/`) |

When OCUDU symptoms point at the UE side, switch to the `amari-ue` type
(`references/amari-ue/`); whole-run correlation is the job of a higher-level
inspect/run orchestrator, not this module.

## Resolve & scope

The dispatcher runs `scripts/ocudu/resolve.py`, which accepts a `gnb.log`
file, a run directory, an `ocudu-gnb-N-M/` component dir, or a Retina
`test_gnb[...]` dir, and resolves to the latest run directory holding a
`gnb.log`. It prints the resolved run dir, the analysis artifacts present
(`gnb.log`, `stdout.log`, `ocudu_gnb.yml`, `metrics.json`), and a `verdict:`
line; it exits non-zero (`BAIL`) if no `gnb.log` is found or it is empty. **Bail
if the verdict is not OK.** (gNB logs are plain text — there is nothing to
validate beyond presence, so this is resolution + inventory, not a preflight.)

**Scope** — when a `test_gnb[...]` dir holds more than one OCUDU app component
(e.g. `ocudu-gnb-1-1` + `ocudu-gnb-1-2`, or a CU/DU split), `resolve.py` reports
them and notes which one it resolved to; scope explicitly to the component you
mean before going further.

## Efficiency rules (ocudu)

- **Never** read raw `gnb.log` into context — it can be 75k–500k+ lines.
- The CONFIG echo at the top of `gnb.log` (everything between line 2 and the
  first `[CONFIG  ] [I] Worker pool` line — several hundred lines) is verbose and
  redundant with `ocudu_gnb.yml` — skip it unless the user explicitly asks about
  an effective-config value.
- Spill larger results to `<cache-dir>/ocudu-<purpose>-<sha>.txt` (use the
  `ocudu-` prefix) and report the path.
- `stdout.log` is short (typically 30–300 lines; longer for multi-UE runs that
  print the metrics table many times) — safe to read in full when single-UE.
  For multi-UE traffic runs, `head -n 50` plus `tail -n 30` is enough.
- `ocudu_gnb.yml` is short (100–200 lines) — safe to read in full. Beware that
  the file is a **concatenation of multiple YAML documents** with no `---`
  separators; later keys override earlier ones (e.g. `all_level: info` then
  `all_level: warning`). See `config-format.md`.
- `metrics.json` is a standard JSON array of per-period records — parse it with
  `python3 -c 'import json; json.load(open("metrics.json"))'`, never `cat` it
  into context. The summary script rolls it up already.
- In multi-UE mode, scope grep queries by `ue=N` or `c-rnti=0xNNNN` early.

For UE-lifecycle latency questions, see `latency-profiling.md`.

## Memory routing (ocudu)

Match the surrounding format; no dates/timestamps.

- new grep recipe → `log-format.md` § Key grep recipes
- new layer / message / keyword → the matching table in `log-format.md`
  (§ Layer tags, § Procedure markers, § Common structured fields)
- new YAML field / quirk → `config-format.md` (§ Sections, § Common overrides,
  § Field reference)
- failure signature / diagnostic step → `procedures/<proc>.md`
  (§ Investigation checklist or § Expected sequence)
- a new `procedures/<name>.md` → also add a row to `analysis-guide.md`
  § Investigating a failure; a new `scripts/ocudu/<name>.py` → document it in
  `analysis-guide.md` and/or the procedure file
- a script bug → fix it in `scripts/ocudu/*.py`
