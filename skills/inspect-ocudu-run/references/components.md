# Components & routing

How a Retina `test_gnb[...]` directory is laid out, which sub-skill owns each
artifact, and how `testbed.json` maps components to the network.

## Directory layout

```
test_gnb[<params>]/
├── testbed.json            # component -> address:port (a Python repr, NOT JSON)
├── test.html               # Retina result summary
├── ocudu-gnb-1-1/          # (or split: ocudu-cu-cp-*, ocudu-cu-up-*, ocudu-du-*)
│   ├── agent-log-*.log      # Retina agent log (SUT lifecycle, SIGTERM/SIGKILL)
│   └── YYYY-MM-DD_HH-MM-SS/  # the run subdir (occasionally artifacts are flat)
│       ├── gnb.log  stdout.log  ocudu_gnb.yml  metrics.json  ps_info_gnb.txt
│       └── rlc.pcap  ngap.pcap  f1ap.pcap  e1ap.pcap  mac.pcap   # whichever enabled
├── amarisoft-ue-1/ … amarisoft-ue-N/
│   └── YYYY-MM-DD_HH-MM-SS/ {ue.log, stdout.log, amarisoft_ue.cfg, metrics.json}
└── amarisoft-5gc-1[-1]/
    └── YYYY-MM-DD_HH-MM-SS/ {mme.log, amarisoft_mme.cfg, ps_info_ltemme.txt}
```

`run_inventory.py` resolves all of this (latest run subdir per component, flat
fallback, artifact list, clock anchors).

## Routing table

| Component dir prefix | Role | Sub-skill |
|---|---|---|
| `ocudu-gnb-*` | integrated gNB | `analyze-ocudu-gnb-log` |
| `ocudu-du-*` | DU (split) | `analyze-ocudu-gnb-log` |
| `ocudu-cu-*`, `ocudu-cu-cp-*`, `ocudu-cu-up-*` | CU / CU-CP / CU-UP (split) | `analyze-ocudu-gnb-log` |
| `ocudu-odu-*`, `ocudu-ocu-*` | O-DU / O-CU variants | `analyze-ocudu-gnb-log` |
| (any of the above) `*.pcap` | NGAP/F1AP/E1AP/MAC/RLC captures | `analyze-pcap` |
| `amarisoft-ue-*` | UE simulator | `analyze-amari-ue-log` |
| `amarisoft-5gc-*` / `amarisoft-mme-*` | 5GC / MME | light-touch here (future `analyze-amari-5gc-log`) |

All OCUDU app logs share the same log format, so `analyze-ocudu-gnb-log` handles
`gnb.log`, `du.log`, `cu*.log` alike.

## testbed.json

A **Python `repr`** of an OrderedDict of `NodeInfo(address=..., port=...)` — not
valid JSON, so it cannot be `json.load`ed. `utils.parse_testbed()` extracts
`component -> {address, port}` by regex. Use it to:
- map a component name to its container IP (e.g. which UE simulator IP appears in
  a pcap's GTP-U / SCTP endpoints);
- confirm which gNB a UE/5GC was wired to in multi-gNB tests.

Multi-UE tests list every UE (`amarisoft-ue-1 … -64`) on one IP with incrementing
ports — they are virtual UEs inside one `lteue` process. `run_inventory.py`
collapses them to a range line.

## 5GC light-touch (until a sub-skill exists)

`mme.log` uses the Amarisoft format (`HH:MM:SS.mmm [LAYER] ...`, UTC, with a
`# Started on` anchor). Useful greps:
```bash
grep -nE "\[NAS\].*(Registration|Service|PDU session|Deregistration)" mme.log | head -50
grep -nE "\[NGAP\]|\[GTPC\]|\[E\]" mme.log | head -50
```
The 5GC NAS UEID (e.g. `[NAS] UL 0064`) maps to the gNB `amf_ue=` (0x0064 = 100).
Keep 5GC findings light here; deep 5GC log knowledge belongs in a future
`analyze-amari-5gc-log` sub-skill, not in this orchestrator.
