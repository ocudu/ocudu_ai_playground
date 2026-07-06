# Troubleshooting: data session failure

The UE attached but data did not flow, or CBR loss was high. For the expected
PDU-session sequence and traffic-stats interpretation, see
`../reference/data-session.md`.

## Investigation checklist

### UE attached but zero throughput

1. Confirm PDU session was established (reconfiguration without reconfigurationWithSync):
   ```bash
   grep -n "DCCH-NR: RRC reconfiguration" ue.log
   grep -n "reconfigurationWithSync {" ue.log
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
   grep -n "reconfigurationWithSync {" ue.log
   ```
   HO-related loss: brief (< 100 ms). Sustained loss → DRB config issue or UPF routing.

3. Check PHY errors:
   ```bash
   grep -n "crc=FAIL" ue.log | wc -l
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

## Cross-references

- ../reference/data-session.md — the expected sequence this walks against.
