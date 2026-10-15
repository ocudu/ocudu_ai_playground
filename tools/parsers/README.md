# Parsers

Decoders and parsers for OCUDU artifacts (logs, pcaps, traces, etc.).

Standard-library only, so it can be imported by visualization or analysis tools without pulling in their dependencies.

## Layout

| Subpackage    | Artifact                                                      |
|---------------|---------------------------------------------------------------|
| `parsers.log` | The text outputs of OCUDU applications: log line preamble, `METRICS` lines, events, the configuration echo, entry search, UE procedure stage latencies and a log summary; and the console output (`stdout.log`), `metrics.json` and the files of a run directory. |
| `parsers.pcap` | The pcaps of a run (`mac`, `rlc`, `f1ap`, `e1ap`, `ngap`), through `tshark`: UE identifiers, F1AP messages with their RRC and NAS messages, NGAP procedures, overviews and a merged timeline. |
| `parsers.ran` | 3GPP knowledge shared by the artifacts: NGAP, F1AP and E1AP procedure codes, NAS and RRC message types. |
| `parsers.schedtrace` | Scheduler event traces (`schedtrace_cell<N>.bin`): the FlatBuffers cell events of the OCUDU scheduler, per slot its inputs and decisions. |
| `parsers.correlate` | Correlation of the artifacts of a run: the UEs that its logs and pcaps see, each with the identifiers of all of them. |

## Installation

```bash
pip install -e tools/parsers            # core, standard library only
pip install -e "tools/parsers[pandas]"  # adds to_dataframe()
```

## Usage

### Metrics

```python
from parsers.log import metrics

parser = metrics.MetricsParser()        # all layers, or e.g. MetricsParser(["sched", "mac"])
with open("gnb.log") as f:
    for line in f:
        rec = parser.parse(line)
        if rec and rec["layer"] == "sched":
            print(rec["timestamp"], rec["total_dl_brate"], parser.units["sched"]["total_dl_brate"])

df = metrics.to_dataframe(open("gnb.log"), "mac")  # units in df.attrs["units"]
```

`parser.parse_file()` parses a whole log, yielding `(line_no, record)` in file order. It splits the log into ranges
that start at log entries (`parsers.log.chunks`), so that memory does not grow with the log. Given an executor, it
parses them in its workers, which is several times faster on large logs:

```python
import multiprocessing
from concurrent.futures import ProcessPoolExecutor

from parsers.log import metrics

if __name__ == "__main__":  # needed by worker processes that start with "spawn" or "forkserver"
    parser = metrics.MetricsParser()
    with ProcessPoolExecutor(mp_context=multiprocessing.get_context("forkserver")) as executor:
        for line_no, rec in parser.parse_file("gnb.log", executor):
            ...
    print(parser.units)  # merged from all ranges once the iteration ends
```

Records are flat dicts with `timestamp`, `layer`, the line context fields (e.g. `pci`) and the metric fields:

- Units are normalized: times to `us`, bitrates to `bps`, SI-prefixed unitless values (`5.74k`) to plain numbers.
  The unit of each field is in `parser.units[layer][field]`.
  Fields that OCUDU prints without a unit (e.g. `dl_bs` in bytes, `pusch_snr_db` in dB) get the one in
  `metrics.IMPLIED_UNITS`.
- `n/a`, `NaN` and `ovl` become `None`.
- Slot fields (`sfn.slot`) stay strings. Use `metrics.parse_slot()` to split them.
- `[k=v ...]` blocks and `<section>:` groups are flattened as `<block>_<key>`.
- Number lists stay lists, and `{...}` record lists become lists of dicts.

Supported layers (keys of `metrics.LAYER_PATTERNS`), matching the current OCUDU log format:

| Layer            | Log line prefix            |
|------------------|----------------------------|
| `du_manager`     | `DU manager metrics:`      |
| `mac`            | `MAC cell pci=N metrics:`  |
| `sched`          | `Scheduler cell pci=N metrics:` |
| `sched_ue`       | `Scheduler UE ue=N pci=N rnti=X metrics:` |
| `rlc`            | `RLC Metrics:`             |
| `phy`            | `PHY metrics:` (first line only) |
| `ofh_timing`     | `OFH timing metrics:`      |
| `ofh_sector`     | `OFH sector#N metrics:`    |
| `pdcp`           | `PDCP Metrics:`            |
| `nrup`           | `NRUP Metrics:`            |
| `e1ap`           | `CU-UP E1AP metrics:`      |
| `exec`           | `Executor metrics "name":` |
| `resource_usage` | `App resource usage:`      |
| `buffer_pool`    | `Buffer pool:`             |

Unit conflicts and unknown units are reported once per field on the `parsers` logger.

### Events

```python
from parsers.log import events

with open("gnb.log") as f:
    for line_no, ev in events.iter_events(f):
        print(line_no, ev["timestamp"], ev["category"], ev["type"], ev["ue"], ev["rnti"], ev["text"])
```

`events.iter_events()` recognizes the lines of known events (`events.EVENT_PATTERNS`) and reports the other warning and
error lines as generic `warning` and `error` events, with the `ue=` and RNTI of their message if any. Records have `timestamp`, `type`, `category`, `layer`, `level`,
`ue`, `rnti`, `cause` and `text`. Records of category `events.BINDING` (`ue_config`) are not events: they give
`events.UeTracker` the RNTI of a UE created without it, e.g. a handover target.

| Category    | Types                                                              |
|-------------|--------------------------------------------------------------------|
| `ra`        | `prach`, `msg3`, `conres`                                          |
| `lifecycle` | `ue_create`, `ue_delete`                                           |
| `rrc`       | `rrc_setup_complete`, `rrc_release`, `rrc_reest_request`           |
| `mobility`  | `ho_trigger`, `ho_preparation`                                     |
| `failure`   | `rlf`, `rrc_reest_failed`, `rrc_reest_rejected`, `conres_timeout`, `rrc_setup_timeout` |
| `warning`   | `warning` (other `[W]` lines)                                      |
| `error`     | `error` (other `[E]` lines)                                        |

A log entry can hold several events, and some messages change format with the log level: the scheduler prints its slot
events inline at info level (`prach(...)`, one event per preamble) and one per continuation line at debug level
(`- PRACH: ...`). Patterns are bound to the level of the entry. To read a log line by line without `iter_events()`, pass
the continuation lines of the entries for which `events.has_body()` is true to `events.parse()`.

### Configuration

```python
from parsers.log import config

cfg = config.from_log(open("gnb.log"))  # None if the log has no configuration echo
if cfg and not cfg.logs_at("SCHED", "info"):
    print("no PRACH events: mac_level is", cfg.level("mac"))
```

`config.from_log()` reads the configuration that OCUDU echoes at the top of its logs (`config_level` info or debug), and
`config.parse_config()` a YAML configuration file. `AppConfig` has the explicit log levels, the effective level of each
option or logger (`level()`, `logger_level()`, `logs_at()`), and the node planes and type.

### Pcaps

`parsers.pcap` needs `tshark` on the `PATH`.

```python
from parsers.pcap import f1ap, ngap, overview, run, timeline
from parsers.pcap.tshark import Tshark

tshark = Tshark()  # stages pcaps and caches extractions in a work directory, by default under the temp dir
pcaps = run.find_pcaps("run_dir")  # {"mac": Path | None, "rlc": ..., "f1ap": ..., "e1ap": ..., "ngap": ...}
for ue in f1ap.ue_ids(tshark, pcaps["f1ap"]):
    print(ue["first_iso"], ue["cu_ue_f1ap_id"], ue["crntis"])
for msg in f1ap.messages(tshark, pcaps["f1ap"]):
    print(msg["first_iso"], msg["message"], msg["rrc"], msg["nas"])
print(overview.summarise(tshark, pcaps["ngap"]))
events = timeline.run_events(tshark, "run_dir", ["ngap", "f1ap"], ue="0")
```

`tshark` reads pcaps through a link or copy in the work directory, since the AppArmor profile of `tshark` on Ubuntu
only lets it read under `/tmp`, and dissects the MAC and RLC PDUs of `mac.pcap` and `rlc.pcap` through the
`mac_nr_udp` and `rlc_nr_udp` heuristics. A pcap whose last record is cut short, e.g. by a crash, gives its complete
records, with a warning. Field extractions are cached in the work directory by pcap path, size and mtime, and a tag, by
default the fields and filter. `run.find_pcaps()` finds the pcaps of each protocol by file name, `<proto>.pcap` or with
a prefix, e.g. `gnb_f1ap.pcap`.
`run.check_pcap()` checks that a pcap has a frame that one of the known dissectors binds. `messages.messages()` lists
the NGAP, F1AP or E1AP messages of a pcap with their procedure, outcome, UE identifiers and cause, `frames.summaries()`
the one-line tshark summary of each frame and `frames.decode()` decodes one frame. `frames.time_span()` reads the time
span of a pcap from its packet headers, without `tshark`. `capture.read()` gives the protocol, the frame summaries and
the messages or PDUs of a pcap in one pass over its frames, after reading its first frame for the protocol.
`contexts.ContextTracker` assigns the NGAP, F1AP or E1AP messages to UE contexts, by their UE identifiers until the
release of the context, with the C-RNTI of the F1AP ones.

### Scheduler event traces

```python
from parsers import schedtrace

for ev in schedtrace.read("schedtrace_cell0.bin"):
    if ev["type"] == "CellSlotEvent":
        harq = [i for i in ev["inputs"] or [] if i["type"] == "HarqAckEvent"]
        print(ev["timestamp_us"], ev["slot_tx"], ev["latency_us"], len(ev["decision"]["ue_pdschs"] or []), harq)
```

OCUDU writes one `schedtrace_cell<N>.bin` per cell when the `trace.schedtrace` option is enabled: an 8-byte header
(magic `SCHT`, then the major and minor version of the file format as little-endian `uint16`) and a series of
size-prefixed FlatBuffers `CellEvent` buffers. `read()` and `events()` yield each as a dict with `timestamp_us`,
`type` (`CellStartEvent`, `CellSlotEvent` or `CellStopEvent`) and its fields: tables as dicts, vectors as lists, enums
by name, unions with their member as `type`, absent optional fields as `None`. An incomplete last event, e.g. of a
trace being written, is left out. A size prefix over `MAX_EVENT_SIZE` (1 MiB) is corrupt: the events from it are left
out, with a warning.

`schedtrace.FORMAT_VERSION` is the version of the schemas of `schedtrace/fbs/`, from their `FileFormatVersionMajor`
and `FileFormatVersionMinor` enums. Traces of another major version, and traces without a header, written before OCUDU versioned the
format, raise `schedtrace.FormatError`; traces of a newer minor version decode with a warning, without the fields they
append. `schedtrace.version()` reads the version of a trace.

The decoder is standard-library only: `schedtrace.schema` reads the FlatBuffers schemas of `schedtrace/fbs/`, copies of
`lib/scheduler/trace/fbs` of OCUDU, and `schedtrace.flatbuf` decodes buffers with them. FlatBuffers' Python code
generator does not support the vectors of unions of the schemas (`CellSlotEvent.inputs`). Decoding uses
`schedtrace/_generated.py`, which `schedtrace.codegen` compiles from the schemas into one function per table and
struct, about 2.3 times faster than `schedtrace.flatbuf`. With `grid_only=True`, `read()`, `events()` and `event_at()`
decode only the fields of `codegen.GRID_FIELDS`, those that `grid.allocations()` needs and the slot, latency and input
types, 1.6 times faster again. When OCUDU changes the schemas, copy them from an OCUDU tree, its working tree or a
revision, and regenerate it:

```bash
python -m parsers.schedtrace.codegen --ocudu ~/srs/ocudu [--rev origin/dev]
```

`_generated.py` holds the file format version and the hash of the schemas, the generator and the schema parser, and a
test fails when it is stale. The tests compare the decoder with flatc on a trace that `tests/schedtrace/data/make_fixtures.sh` builds, and
the generated decoder with `schedtrace.flatbuf`. It decodes about 18k slots per second of busy slots.

`schedtrace.collisions` finds the allocations of a slot whose resources overlap: PDSCH with PDSCH, PUSCH with PUSCH,
PUSCH with PUCCH, PDCCH with PDSCH, and PDCCH with PDCCH, by their CCEs in a CORESET. PDSCHs are placed as `grid.allocations()` places
them: those of DCI format 1_0 in a common search space (SIB, RAR, paging, fallback), matched to their PDCCH in the slot,
from the lowest CRB of its CORESET (TS 38.214 5.1.2.2.2), the others from the BWP start; PDCCHs from the REG bundles
of their CCEs (TS 38.211 7.3.2.2). `skills/analyze-ran-log/scripts/ocudu/schedtrace_collisions.py` prints them.

`schedtrace.ue_metrics` gives the per-UE metrics of a trace: `slot_items()` the DL and UL grants, HARQ-ACK and CSI
reports and SRs of a slot, per UE, and `Aggregator` their sums per UE and 10 ms bin, as rows named after the fields of
the METRICS `Scheduler UE` lines where they mean the same (`dl_brate` from the ACKed TBS, `dl_mcs`, `dl_nof_ok`,
`dl_error_rate`, `cqi`, `dl_ri`, `sr_count`), plus the scheduler latency, PRBs and UEs of the cell per bin.
Aggregators of parts of a trace merge; `Aggregator(bin_s=1)` gives 1 s bins, as METRICS periods, and `ue_totals()` the
totals of each UE over a span. `skills/analyze-ran-log/scripts/ocudu/schedtrace_ue_metrics.py` prints them. The trace has no UL CRC or buffer status: UL rates are of scheduled new
transmissions (`ul_sched_brate`), and a DTX report counts as not ok.

```python
from parsers import schedtrace
from parsers.schedtrace import grid, ue_metrics

events = schedtrace.read("schedtrace_cell0.bin", grid_only=True)
cell = grid.cell_of(next(events))
agg = ue_metrics.Aggregator()
for record, ev in enumerate(events, 2):
    if ev["type"] == "CellSlotEvent":
        agg.add(record, ev, ue_metrics.slot_items(ev, cell))
for t, record, *values in agg.ue_rows():
    print(t, dict(zip(ue_metrics.UE_FIELDS, values)))
```

### Ad-hoc metrics of logs

`parsers.log.adhoc` scans a byte range of a log for the numeric values of a `key=value` field, e.g. `tbs=` of the slot
decision lines, optionally in the lines matching a regex and split by the nearest value of another key before each
value in its line. Values with a unit are scaled as METRICS fields are. Ranges of `chunks.chunk_ranges()` scan
independently. Without a key, `scan_lines()` gives the lines matching the regex, with their text, logger, level, UE
index and RNTI.

```python
import os

from parsers.log import adhoc

spec = adhoc.Spec("tbs", filter="slot decisions", split_key="ue")
res = adhoc.scan("gnb.log", 0, os.path.getsize("gnb.log"), 1, spec)
for t, line, offset, value, ue in res["rows"]:
    print(t, line, value, ue)
```

### Log search, summary and UE procedure latencies

```python
from parsers.log import procedures, run, search, summary

log = run.find_log("e2e/log/tests/.../ocudu-gnb-1")      # the log of the latest run under a directory
with open(log, errors="replace") as f:
    for entry in search.search(f, search.Filter(layer="RRC", rnti="4601", after="18:18:30")):
        print(entry)
with open(log, errors="replace") as f:
    s = summary.summarize(f)                              # build, NG setup, cells, UE lifecycle, counters
with open(log, errors="replace") as f:
    found = procedures.instances(f)                      # per procedure, its instances with stage times
mac = found["MAC UE Creation"]
print(procedures.stats(procedures.latencies(mac, "start", "done")))
```

Search entries are a timestamped line and its continuation lines, so filters match ASN.1 bodies too, and the
configuration echo is left out unless asked for. Procedures are the `proc="..."` traces of the DU (`PROCEDURES`):
stages that a build does not log are skipped. `console.summarize()` reads the console output of an application,
`metrics_json.rollup()` its `metrics.json`, and `config.parse_config()` also gives the cell, AMF, duplex and pcap
options. The `ocudu_log_search.py`, `ocudu_log_summary.py` and `ocudu_ue_proc_latency.py` scripts of the
analyze-ran-log skill print them.

### UEs of a run

`parsers.correlate.ues.combine()` combines the UE contexts that the sources of a run see, the most reliable source
first, into one UE each with the identifiers of all of them:

```python
from parsers.correlate.ues import Context, combine

f1ap = [Context("f1ap.pcap", 0, 10.0, 20.5, {"rnti": "17921", "du_f1ap": "0", "cu_f1ap": "0"})]
log = [Context("gnb.log", 0, 9.9, 20.5, {"du_ue": "0", "rnti": "0x4601"})]
for ue in combine(f1ap, log):
    print(ue.key, ue.ids, ue.parts)  # f1ap.pcap:0 {"rnti": ["0x4601"], "du_f1ap": ["0"], "cu_f1ap": ["0"], "du_ue": ["0"]} ...
```

A context of a later source joins a UE of an earlier one by RNTI with overlapping lifetimes, a UE still open at the end
of its sources living to that end, or without RNTI by creation time, e.g. the target of a handover, which a log creates
before it knows its RNTI. RNTIs are compared as
`parsers.ran.rnti` normalizes them.

`parsers.correlate.run` reads the contexts from the files: `log_contexts()` from an OCUDU log (`events.UeTracker`),
`pcap_contexts()` from an NGAP, F1AP or E1AP pcap (`parsers.pcap.contexts`), `run_ues()` combines the F1AP pcap
and the logs of a run, and `run_traces()` also follows each UE through its contexts and its NGAP and E1AP contexts
(`ues.ue_traces()`): handovers by target C-RNTI, reestablishments by old C-RNTI, NGAP by NAS PDU or handover C-RNTI, E1AP
by UPF TEID:

```python
from parsers.correlate.run import run_traces
from parsers.pcap.tshark import Tshark

ues, traces = run_traces(Tshark(), "run_dir/f1ap.pcap", ["run_dir/gnb.log"], ["run_dir/ngap.pcap", "run_dir/e1ap.pcap"])
for ue in ues:
    print(ue.t_start, ue.first("ue_trace"), ue.first("rnti"), ue.first("du_ue"), ue.first("cu_ue"), ue.first("ran_ngap"))
for trace in traces:
    print(trace.id, len(trace.ues), trace.ids.get("rnti"), trace.ids.get("amf_ngap"))
```

## Tests

```bash
python3 -m unittest discover -s tools/parsers/tests -t tools/parsers
```
