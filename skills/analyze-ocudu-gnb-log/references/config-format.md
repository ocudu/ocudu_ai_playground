# OCUDU YAML Config Reference

## File: ocudu_gnb.yml

The config file the OCUDU gNB was started with. Retina builds it by
concatenating templates — there are usually multiple `log:`, `metrics:`,
`pcap:`, and `cu_cp:` blocks, separated by visible SPDX comment headers but
**not** by `---` YAML document separators. The parser treats them as one
document and **later keys override earlier ones**.

This is what the user sees on disk — it is the **input**, not the effective
config. The effective config (with defaults filled in) is echoed at the top of
`gnb.log` under the `[CONFIG  ] [D] Input configuration (all values):` block.

### Reading shortcut

```bash
ls -lh ocudu_gnb.yml
wc -l ocudu_gnb.yml
cat ocudu_gnb.yml      # 100–200 lines, safe to read in full
```

When the user asks "what was X set to", search both the YAML (what was
requested) and the CONFIG echo (what was effective):

```bash
grep -nE "^[ ]*X:" ocudu_gnb.yml          # user-supplied
sed -n '2,/Worker pool/p' gnb.log | grep -nE "^[ ]*X:"   # effective
```

---

## Sections

The Retina template typically stitches these blocks (in order):

1. **Boot-level overrides** — bare `log.filename`, `log.all_level`,
   `gnb_id`, `metrics.enable_log`.
2. **Baseline log/PCAP block** — second `log:` map plus `pcap:` enabling
   `ngap`/`f1ap`/`e1ap` captures. Often raises layer-specific verbosity
   (`rrc_level: warning`, `pdcp_level: warning`, etc.) so use this to predict
   which layers will actually emit in `gnb.log`.
3. **Baseline single-slice config** — `cu_cp.amf.supported_tracking_areas`.
4. **Cell config** — `cell_cfg` (pci, band, bandwidth, antennas, ARFCN, PRACH).
5. **Per-test pcap/log overrides** — flips on `pcap.rlc_enable`, raises
   `all_level: info` again for tests that need RRC traces.
6. **Metrics block** — `metrics.autostart_stdout_metrics`,
   `metrics.layers.enable_sched|enable_mac|enable_du_proc`.
7. **RU/radio block** — `ru_sdr` with sample rate, ZMQ port mapping,
   `time_alignment_calibration`, `expert_cfg.low_phy_dl_throttling`.
8. **AMF address block** — second `cu_cp.amf` with `addrs`/`port`/`bind_addrs`.
9. **Remote control** — `remote_control.enabled`, `bind_addr`.

When two blocks set the same key, the **last one wins**. The classic gotcha
is `log.all_level`: the baseline block sets it to `warning`, then the
per-test block resets it to `info`. To know what actually applied, look at
the `[CONFIG  ] [D]` echo at the top of `gnb.log`.

---

## Common overrides and what they enable

| Knob | Default-ish | Effect on `gnb.log` |
|---|---|---|
| `log.all_level: info` | required for RRC/NGAP traces | Everything below also raises to info unless overridden |
| `log.rrc_level: info` | warning | RRC CCCH/DCCH per-message lines appear |
| `log.ngap_level: info` | warning | `Tx/Rx PDU` for NG setup + UE-associated procedures |
| `log.f1ap_level: info` | warning | F1AP `Tx/Rx PDU` per UE message |
| `log.e1ap_level: info` | warning | E1AP `Tx/Rx PDU` (bearer context lifecycle) |
| `log.pdcp_level: info` | warning | `[PDCP] TX/RX PDU` per SDU (very chatty under traffic) |
| `log.mac_level: info` | info | Per-PDU MAC details |
| `log.phy_level: info` | info | PDCCH/PDSCH/PUCCH/PUSCH per-slot lines (very chatty) |
| `log.sec_level: info` | warning | Logs K_gNB and derived keys (often blank when `hex_max_size: 0`) |
| `log.hex_max_size: N` | 0 | Bytes of hex dump shown per PDU; 0 = none, 32 = trimmed, large = full |
| `log.config_level: debug` | info | Includes the giant `[CONFIG  ] [D] Input configuration` echo |
| `metrics.enable_log: true` | false | Emits `[METRICS]` rows in `gnb.log` |
| `metrics.enable_json: true` | false | Writes `metrics.json` |
| `metrics.autostart_stdout_metrics: true` | false | Prints the metrics table in `stdout.log` |
| `metrics.layers.enable_sched: true` | false | Scheduler-level metrics row |
| `metrics.layers.enable_mac: true` | false | MAC latency snapshot |
| `metrics.layers.enable_du_proc: true` | false | Per-UE DU processing latency |
| `pcap.rlc_enable: true` | false | Writes `rlc.pcap` |
| `pcap.ngap_enable: true` | false | Writes `ngap.pcap` |
| `pcap.f1ap_enable: true` | false | Writes `f1ap.pcap` |
| `pcap.e1ap_enable: true` | false | Writes `e1ap.pcap` |
| `pcap.mac_enable: true` | false | Writes `mac.pcap` (Upper-PDU MAC-NR frames) |

When a user asks "why do I not see X in the log?", first check the matching
`log.<layer>_level` knob.

---

## Field reference (frequently consulted)

| Path | Type | Notes |
|---|---|---|
| `gnb_id` / `gnb_id_bit_length` | int | gNB identity for NGAP setup |
| `ran_node_name` | string | Cosmetic identifier echoed at NGAP setup |
| `cell_cfg.pci` | int | Physical Cell ID |
| `cell_cfg.band` | int | NR band (e.g. 3, 78) |
| `cell_cfg.dl_arfcn` | int | DL ARFCN (centre frequency) |
| `cell_cfg.channel_bandwidth_MHz` | int | Cell bandwidth (5, 10, 20, 50, 100) |
| `cell_cfg.common_scs` | int | Numerology SCS in kHz (15, 30, 60) |
| `cell_cfg.nof_antennas_dl` / `nof_antennas_ul` | int | MIMO layout (1, 2, 4) |
| `cell_cfg.prach.prach_config_index` | int | PRACH preamble format / occasion table |
| `cell_cfg.tdd_ul_dl_cfg.*` | map | TDD pattern; presence implies TDD mode |
| `cu_cp.amf.addrs` | scalar or list | AMF SCTP target IP(s). In the example runs it is a **scalar** (`addrs: 172.20.0.10`); the summary script's regex matches the scalar form |
| `cu_cp.amf.port` | int | AMF SCTP port (default 38412) |
| `cu_cp.amf.bind_addrs` | scalar or list | Local bind address(es) for N2 (scalar in the example runs) |
| `cu_cp.amf.supported_tracking_areas` | list | TAC + PLMN + slice (sst/sd) advertised at NG setup |
| `cu_cp.mobility.trigger_handover_from_measurements` | bool | If true, the gNB initiates HO from RRC meas reports |
| `cu_cp.security.integrity` / `confidentiality` | enum | `not_needed` / `preferred` / `required` |
| `cu_cp.security.nea_pref_list` / `nia_pref_list` | csv | Algorithm preference |
| `ru_sdr.device_driver` | string | `zmq` for simulated tests, `uhd` for real radios |
| `ru_sdr.device_args` | string | Comma-separated driver args (ZMQ ports, base_srate, id) |
| `ru_sdr.srate` | float | Sample rate in MHz |
| `ru_sdr.sync` / `time_alignment_calibration` | enum | Radio sync source / TA cal mode |
| `ru_sdr.expert_cfg.low_phy_dl_throttling` | int | DL throttling level (0 = none) |
| `remote_control.enabled` / `bind_addr` / `port` | mixed | gNB remote control TCP server |
| `slicing[].sst` / `slicing[].sd` | mixed | Network slice support (matches what AMF expects) |
| `pcap.<proto>_filename` | path | Output PCAP path; pairs with `<proto>_enable` |

### Multi-document gotcha

The YAML in `ocudu_gnb.yml` is **not** standard multi-document YAML. There are
no `---` separators — Retina just concatenates strings. This means:

- Comments and SPDX banners appear in the middle of the document.
- Some keys (like `log:` and `metrics:`) appear two or three times.
- Tools like `yq '.log'` will silently return only the **last** `log:` map.

If you need merged-view, parse the file as raw YAML with PyYAML's loader and
expect duplicate-key warnings — or just read the file top-to-bottom and apply
overrides in order.

---

## Quick checks

```bash
# What layers will produce traces?
grep -E "^\s*(all_level|rrc_level|ngap_level|f1ap_level|e1ap_level|pdcp_level|mac_level|phy_level|sec_level|config_level|hex_max_size):" ocudu_gnb.yml

# Cell parameters at a glance
grep -A 20 "^cell_cfg:" ocudu_gnb.yml | head -25

# AMF endpoint
grep -A 5 "^cu_cp:" ocudu_gnb.yml | grep -E "addrs|port|bind_addrs"

# Radio config
grep -A 10 "^ru_sdr:" ocudu_gnb.yml

# Which PCAPs were enabled?
grep -E "_enable: true" ocudu_gnb.yml
```
