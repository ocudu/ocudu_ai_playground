# UE-lifecycle latency profiling

Load this only when the task is *how long UE creation / reconfiguration /
removal takes* (per-stage and end-to-end). For everyday overviews/failures it is
not needed.

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/ocudu/ocudu_ue_proc_latency.py <gnb.log> [proc-filter-substr]
```

**Prerequisite — L2 log levels.** The DU/MAC `proc="..."` traces this tool keys
on are emitted only when `du_level` (DU-manager) and `mac_level` (MAC; also gates
SCHED — there is no `sched_level`) are at `info`/`debug`. In a Release build or
any run with these at `warning` the traces are absent and the profiler prints
nothing — this is a config artifact, not a fast run. Check the summary's
`Log levels` / `L2 traces` line first (run `ocudu_log_summary.py`); if it reports
L2 traces suppressed, the per-stage latencies are simply unavailable from that
log. Note this also means a monolithic gNB log can look CU-only at a glance when
only `rrc`/`cu` are at `info`.

Reconstructs every UE-lifecycle procedure instance and reports per-stage and
total latency (n, mean, p50, p90, p99, max), grouped into CREATION
(`UE Create` + `MAC UE Creation`), CONFIGURATION (`UE Configuration` +
`MAC UE Reconfiguration` + `Sched UE Config`) and REMOVAL (`UE Delete` +
`MAC UE Removal` + `UE Context Release`). The optional second arg filters by a
procedure-name substring (e.g. `"UE Delete"`).

Key properties:

- **Declarative + graceful degradation.** Stages live in a registry of
  `proc="..."` markers. Builds that emit only `Procedure started/finished` yield
  the end-to-end total; builds with the granular MAC/DU stage traces get the
  full per-stage breakdown. Absent stages are skipped (`n=0`), so the same tool
  works on mainline and instrumented branches.
- **Instance-correct.** Records are keyed per `(ue, procedure)` and re-opened on
  each procedure start, so UE-id reuse across re-creations and multiple
  reconfigurations per UE are counted as separate instances.
- **Parallel-stage aware.** Procedures may define explicit transitions
  (`TRANSITIONS`) for stages that race — e.g. MAC UL/DL context creation is
  measured from MAC start, and the commit from `max(UL, DL)`.

Reading the output: a flat, low-variance stage (small mean≈p99 gap) points at a
fixed timer; a large mean-vs-p50 gap points at burst/queue contention. Compare
branches/builds on mean + tail to see which phase dominates.

Extending it: add an entry to the `PROCS` registry (procedure name → ordered
`(stage_key, exact_label)` list) and, for racing stages, a `TRANSITIONS` entry.
