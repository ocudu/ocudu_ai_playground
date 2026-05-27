# Data session procedure

## Expected sequence (PDU session establishment)

After initial registration, the AMF triggers PDU session setup:

```
[NAS]   0001 New state : 5GMM-REGISTERED CM-CONNECTED
[RRC]   DL 0001 00 DCCH-NR: RRC reconfiguration   ← PDU session config (no reconfigurationWithSync)
[RRC]   UL 0001 00 DCCH-NR: RRC reconfiguration complete
  ↓ (DRB established, data flows)
[PROD]  SIM-Event: cbr_recv    ← CBR DL traffic starts
[PROD]  SIM-Event: cbr_send    ← CBR UL traffic starts
```

In stdout.log, data flow appears as non-zero `brate` values in UE stats rows.

## Traffic stats interpretation

### CBR (constant-bit-rate) traffic

```
[addr:2000] CBR_RECV: sent=N, recv=M   ← DL: gNB sent N, UE received M
[addr:2001] CBR_SEND: sent=N, recv=M   ← UL: UE sent N, gNB received M
```

`recv < sent` indicates packet loss. Expected: 0% loss on a clean run.
Acceptable during HO: brief spike corresponding to the HO duration.

### PHY throughput from stats table (stdout.log)

```
UE_ID  RAT CL RNTI   CFO   SRO  SINR  RSRP  mcs retx rxfail txok brate     #its  mcs  ta retx   tx brate
    1   NR 00 4601     0  -0.0 100.3 -36.8 26.5    0      0 1999 21.1M  1/2.4/3 27.0   0    0 1128 10.3M
```

Key columns:
- `SINR` (dB): signal quality. Should be > 20 dB for max MCS.
- `RSRP` (dBm): reference signal received power.
- `mcs`: modulation/coding scheme used (0-28 for NR).
- `retx`: DL retransmission count. Non-zero → HARQ errors.
- `rxfail`: DL receive failures.
- `txok`/`brate`: DL good TB count / bitrate.
- `#its`: HARQ iterations (min/avg/max). `1/1.0/1` = always 1 attempt (ideal).
- UL `retx`: UL retransmissions.
- UL `brate`: UL bitrate.

## Investigation checklist

### UE attached but zero throughput

1. Confirm PDU session was established (reconfiguration without reconfigurationWithSync):
   ```bash
   grep -n "DCCH-NR: RRC reconfiguration" ue.log
   grep -n "reconfigurationWithSync" ue.log
   ```
   If there is no `RRC reconfiguration` after `5GMM-REGISTERED` → PDU session
   never set up. Check AMF/UPF logs.

2. Check if CBR sim events fired:
   ```bash
   grep -n "SIM-Event" ue.log
   ```
   If `cbr_recv` / `cbr_send` events are absent → traffic was not started
   (sim_event config issue or timing).

3. Check UL/DL activity in stdout:
   - Zero brate in all stats rows → no scheduling.
   - Non-zero brate but CBR loss = 100% → routing issue (UPF/TUN).

### High packet loss

1. Find the loss window:
   ```bash
   # Look at per-second stats in stdout.log for brate drops
   grep -E "NR [0-9]{2} [0-9a-f]+" stdout.log | head -30
   ```

2. Check if loss correlates with a handover:
   ```bash
   grep -n "reconfigurationWithSync" ue.log
   ```
   HO-related loss: brief (< 100 ms). Sustained loss → DRB config issue or UPF routing.

3. Check PHY errors:
   ```bash
   grep -n "crc=FAIL" ue.log | wc -l
   grep -n "rxfail" ue.log   # not useful — that's in stdout
   ```

4. Check HARQ iteration count in stdout stats:
   - `#its` of `1/3.0/3` (max = 3 HARQ rounds) → severe DL channel issues.
   - Non-zero `retx` column → UL HARQ retransmissions.

### Ping test: high RTT or loss

```bash
# ICMP send/recv — ping events appear in PROD layer
grep -n "SIM-Event: ping" ue.log
```

Ping stats are not shown in stdout.log (CBR stats only). Check gNB/5GC side
for ICMP round-trip measurements.

## Accumulated knowledge

<!-- Append new generalisable findings here as they are discovered. -->

- A `sim_events_loop_count > 1` in the cfg means the UE repeats the event
  sequence N times. Each loop includes a power_off + re-attach cycle.
  High CBR loss in loops 2+ but not loop 1 → re-attach or DRB re-setup issue.
- CBR `recv` can exceed `sent` if the CBR sender is on the UE side and the
  ICMP echo-reply comes back through the same counter. Treat `recv > sent` as
  a counting artefact, not actual gain.
