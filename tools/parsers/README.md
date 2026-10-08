# Parsers

Decoders and parsers for OCUDU artifacts (logs, pcaps, traces, etc.).

Standard-library only, so it can be imported by visualization or analysis tools without pulling in their dependencies.

## Layout

| Subpackage    | Artifact                                                      |
|---------------|---------------------------------------------------------------|
| `parsers.log` | OCUDU text logs: line preamble, `METRICS` lines, events and the configuration echo. |
| `parsers.pcap` | The pcaps of a run (`mac`, `rlc`, `f1ap`, `e1ap`, `ngap`), through `tshark`: UE identifiers, F1AP messages with their RRC and NAS messages, NGAP procedures, overviews and a merged timeline. |
| `parsers.ran` | 3GPP knowledge shared by the artifacts: NGAP, F1AP and E1AP procedure codes, NAS and RRC message types. |

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

`parser.parse_file()` parses a whole log, yielding `(line_no, record)` in file order. Given an executor, it splits the
log into ranges that start at log entries (`parsers.log.chunks`) and parses them in its workers, which is several times
faster on large logs:

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
`ue`, `rnti`, `cause` and `text`.

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
`mac_nr_udp` and `rlc_nr_udp` heuristics. Field extractions are cached in the work directory by pcap and fields.
`run.check_pcap()` checks that a pcap has a frame that one of the known dissectors binds. `messages.messages()` lists
the NGAP, F1AP or E1AP messages of a pcap with their procedure, outcome, UE identifiers and cause, `frames.summaries()`
the one-line tshark summary of each frame and `frames.decode()` decodes one frame. `frames.time_span()` reads the time
span of a pcap from its packet headers, without `tshark`. `capture.read()` gives the protocol, the frame summaries and
the messages or PDUs of a pcap in one pass over its frames, after reading its first frame for the protocol.

## Tests

```bash
python3 -m unittest discover -s tools/parsers/tests -t tools/parsers
```
