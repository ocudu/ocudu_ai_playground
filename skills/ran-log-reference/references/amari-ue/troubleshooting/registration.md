# Troubleshooting: registration failure

The UE failed to attach. For the expected attach / deregistration sequences, see
`../reference/registration.md`.

## Investigation checklist

When the UE fails to attach, work through this checklist in order. In multi-UE
runs all UEs share one `ue.log`, so filter by the (hex) UE ID — e.g.
`grep " 0001 " ue.log` — to isolate one UE's sequence.

### 1. Did the UE find a cell?

```bash
grep -n "PSS:\|SIB found\|BCCH-BCH-NR\|BCCH-NR: SIB1" ue.log | head -20
grep "SIB found" stdout.log
```

- If no PSS → UE never locked to a cell. Check RF config (band, ARFCN) in
  `amarisoft_ue.cfg` vs. gNB config.
- If PSS found but no SIB1 → cell barred or SIB decoding issue.
- In multi-cell configs the UE may see several cells (CELL_ID 00, 01, …); it
  selects the one with the strongest RSRP at PSS time for initial access.

### 2. Did PRACH succeed?

```bash
grep -n "PRACH:" ue.log | head -20
grep -n "CCCH-NR: RRC setup" ue.log | head -5
```

- Multiple PRACH with no RRC Setup → network not responding (check gNB RA config).
- PRACH present → look for `RRC setup`.

### 3. Did the RRC Setup complete?

```bash
grep -n "CCCH-NR\|DCCH-NR: RRC setup" ue.log | head -10
grep -n "5GMM-REGISTERED-INITIATED" ue.log | head -5
```

- `RRC setup` DL received but no `RRC setup complete` UL → UE-side issue.
- `RRC setup` missing → network rejected.

### 4. Did NAS registration succeed?

```bash
grep -n "New state" ue.log | grep "5GMM-REGISTERED"
```

- Stuck at `REGISTERED-INITIATED` → authentication or security failure.
  Check for NAS security mode command/complete sequence.
- Never reached `REGISTERED` → AMF rejected (check 5GC/MME logs).

### 5. Did the UE exit cleanly?

```bash
tail -5 ue.log
grep "# Ended on" ue.log
```

- Missing `# Ended on` → abnormal exit (crash or forced kill).

## Cross-references

- ../reference/registration.md — the expected sequence this walks against.
