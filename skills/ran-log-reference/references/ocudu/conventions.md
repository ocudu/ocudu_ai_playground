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

## Subtree layout

Debugging is symptom-first, so the docs split by role:

- **`troubleshooting/`** — symptom → root-cause playbooks (failure markers +
  investigation checklist). Two kinds: cross-cutting diagnostics (abnormal exit,
  PHY / radio-link, HARQ KOs/BLER, throughput degradation, fallback scheduling)
  and per-procedure failure dispatch (attach, no-user-plane, handover,
  reestablishment, UE release, NGAP/AMF). Start here from a symptom; each cites
  the expected-sequence `reference/` doc it needs.
- **`reference/`** — lazily-loaded knowledge: format specs (`log-format.md`,
  `config-format.md`), UCI outcome vocabulary (`uci.md`), and the expected-sequence
  procedure references (attach, PDU session, NGAP setup, handover,
  reestablishment, release). Procedure docs hold the **sequence + vocabulary
  only**; their failure markers and checklists live in the paired
  `troubleshooting/` doc.
- top level — the entry point (`conventions.md`), the methodology + failure
  dispatch (`analysis-guide.md`), the latency profiler (`latency-profiling.md`),
  and how to escalate to the OCUDU source tree (`source-code.md`).

The `analysis-guide.md` § Investigating a failure dispatch table maps each symptom
to the doc to load.

## Deeper knowledge — the OCUDU source docs

These `reference/` docs cover the **log-observable** layer. The code-side layer
beneath it — architecture, threading, why a metric is computed or a procedure
sequenced the way it is — lives in the **OCUDU source tree**. When the docs here
don't go deep enough, escalate to it: `source-code.md` says when to reach for it,
where to find it (in-project → elsewhere under `$HOME` → public repo, with the
permission model), and how to read it (subsystem READMEs, match the build,
read-only).

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
- Skip the CONFIG echo at the top of `gnb.log` (the `[CONFIG  ] [D]` block, several
  hundred lines) unless the user explicitly asks about an effective-config value —
  see `log-format.md` § Header (the CONFIG echo).
- Spill larger results to `<cache-dir>/ocudu-<purpose>-<sha>.txt` (use the
  `ocudu-` prefix) and report the path.
- `stdout.log` is short (typically 30–300 lines; longer for multi-UE runs that
  print the metrics table many times) — safe to read in full when single-UE.
  For multi-UE traffic runs, `head -n 50` plus `tail -n 30` is enough.
- `ocudu_gnb.yml` is short (100–200 lines) — safe to read in full. Beware it is a
  **concatenation of multiple YAML documents** with no `---` separators; later keys
  win (e.g. `all_level: info` then `all_level: warning`) — see
  `reference/config-format.md` § Sections.
- `metrics.json` is a standard JSON array of per-period records — parse it with
  `python3 -c 'import json; json.load(open("metrics.json"))'`, never `cat` it
  into context. The summary script rolls it up already.
- In multi-UE mode, scope grep queries by `ue=N` or `c-rnti=0xNNNN` early.

For UE-lifecycle latency questions, see `latency-profiling.md`.
