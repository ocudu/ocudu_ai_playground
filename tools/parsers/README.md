# Parsers

Decoders and parsers for OCUDU artifacts (logs, pcaps, traces, etc.).

Standard-library only, so it can be imported by visualization or analysis tools without pulling in their dependencies.

## Layout

| Subpackage    | Artifact                                                      |
|---------------|---------------------------------------------------------------|
| `parsers.log` | OCUDU text logs: line preamble and `METRICS` logger lines.    |

## Installation

```bash
pip install -e tools/parsers            # core, standard library only
pip install -e "tools/parsers[pandas]"  # adds to_dataframe()
```

## Usage

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

## Tests

```bash
python3 -m unittest discover -s tools/parsers/tests -t tools/parsers
```
