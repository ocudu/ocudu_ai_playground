# Parsers

Decoders and parsers for OCUDU artifacts (logs, pcaps, traces, etc.).

Standard-library only, so it can be imported by visualization or analysis tools without pulling in their dependencies.

## Layout

| Subpackage    | Artifact                                                      |
|---------------|---------------------------------------------------------------|
| `parsers.log` | OCUDU text logs: line preamble and `METRICS` logger lines.    |

## Installation

```bash
pip install -e tools/parsers
```

## Usage

```python
from parsers.log import metrics

with open("gnb.log") as f:
    for line in f:
        fields = metrics.parse_fields(line, "sched")
        if fields:
            print(fields["timestamp"][0], fields["total_dl_brate"])
```

`parse_fields` returns `{name: (value, unit)}`, or `None` if the line is not a metric of the given layer.
Supported layers are the keys of `metrics.LAYER_PATTERNS` (`mac`, `rlc`, `sched`, `sched_ue`, `exec`, `upper_phy`, `ofh`).

## Tests

```bash
python3 -m unittest discover -s tools/parsers/tests -t tools/parsers
```
