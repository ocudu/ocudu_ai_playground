# Data session procedure

UE-log observation surface. The artifact-agnostic PDU-session ladder is
`../../common/procedures/pdu-session-setup.md`; this file is the UE-side view
(reconfiguration + CBR traffic stats). For diagnosing a *failed* data session,
see `../troubleshooting/data-session.md`.

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
[addr:2000] CBR_RECV: sent N, recv M   ← DL: gNB sent N, UE received M
[addr:2001] CBR_SEND: sent N, recv M   ← UL: UE sent N, gNB received M
```
(Note: space-separated `sent N, recv M` — no `=`.)

`recv < sent` indicates packet loss. Expected: 0% loss on a clean run.
Acceptable during HO: brief spike corresponding to the HO duration.

`recv > sent` is a counting artefact (e.g. a UE-side CBR sender whose echo-reply
returns through the same counter), not actual gain. With
`sim_events_loop_count > 1` the UE repeats the whole event sequence N times, each
loop including a power_off + re-attach — so high CBR loss in loops 2+ but not
loop 1 points at a re-attach or DRB re-setup problem rather than the radio.

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

## Diagnosing failures

For the investigation checklist (and failure markers), see
`../troubleshooting/data-session.md`.
