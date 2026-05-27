# Handover and reestablishment procedures

## Handover (reconfigurationWithSync)

### Expected sequence (inter-cell HO, e.g. CL 00 → CL 01)

```
[RRC]   DL 0001 00 DCCH-NR: RRC reconfiguration
    ...
          reconfigurationWithSync {   ← this line is in the body, not the header
            ...
          }
[RRC]   UL 0001 01 DCCH-NR: RRC reconfiguration complete   ← note: cell 01 now!
```

Key indicator: the `RRC reconfiguration complete` is sent on the **target cell**
(different CL index than the `RRC reconfiguration`). In stdout.log the RNTI also
changes on the next stats row.

### Grep for handovers

```bash
# Count handovers
grep -c "reconfigurationWithSync" ue.log

# Find handover timestamps
grep -n "reconfigurationWithSync" ue.log

# See which cell each reconfiguration complete was sent on
grep -n "DCCH-NR: RRC reconfiguration" ue.log
```

### Distinguishing HO from bearer-only reconfiguration

A `RRC reconfiguration` **without** `reconfigurationWithSync` in its body is a
bearer or measurement config update, not a handover. Confirm with:

```bash
# Get line numbers of all reconfiguration DL messages
grep -n "DL.*DCCH-NR: RRC reconfiguration$" ue.log

# For each line N, check lines N+1 through N+200 for reconfigurationWithSync
grep -A 200 "DL.*DCCH-NR: RRC reconfiguration$" ue.log | grep -m1 "reconfigurationWithSync\|RRC reconfiguration complete"
```

---

## RRC Reestablishment

Triggered when the UE loses the serving cell (RLF). The UE sends a reestablishment
request on any cell it can reach.

### Expected sequence

```
[PHY]   DL 0001 00 ...   ← radio link failure (e.g. T310 expiry, many CRC FAIL)
[RRC]   UL 0001 00 CCCH-NR: RRC reestablishment request
[RRC]   DL 0001 00 CCCH-NR: RRC reestablishment    ← network accepts
[RRC]   UL 0001 00 DCCH-NR: RRC reestablishment complete
[RRC]   DL 0001 00 DCCH-NR: RRC reconfiguration    ← restore bearers
[RRC]   UL 0001 00 DCCH-NR: RRC reconfiguration complete
```

If the network rejects the reestablishment request, it sends `RRC setup` instead,
forcing a full re-attach.

### Grep for reestablishments

```bash
# All reestablishment events
grep -n "reestablishment" ue.log | grep "\[RRC\]"

# Count
grep -c "reestablishment" ue.log

# PHY failures before reestablishment (look for CRC FAIL spike)
grep -n "crc=FAIL" ue.log | head -20
```

---

## Investigation checklist

### HO: expected but not seen

1. Check if HO was supposed to happen (config has multiple cells, or intra-RU HO test):
   ```bash
   grep "reconfigurationWithSync" ue.log | wc -l
   grep -n "DCCH-NR: RRC reconfiguration" ue.log | wc -l
   ```
2. Count all reconfigurations vs. those with sync — if counts differ, some were
   bearer-only.
3. Check if RLF occurred instead of clean HO:
   ```bash
   grep -n "reestablishment\|crc=FAIL" ue.log | head -20
   ```

### HO: seen but UE lost connectivity (CBR loss spike)

1. Find exact HO timestamp:
   ```bash
   grep -n "reconfigurationWithSync" ue.log | head -5
   ```
2. Check reconfiguration complete was sent (expected: ~10–30 ms later on target cell):
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/references/scripts/ue_log_search.py ue.log \
     --layer RRC --pattern "reconfiguration complete" --after <HO-time>
   ```
3. Check PRACH on target cell (CFRA/CBRA RA needed for HO):
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/references/scripts/ue_log_search.py ue.log \
     --layer PHY --pattern "PRACH:" --after <HO-time>
   ```
4. If PRACH retried many times → RA failure; if no PRACH → UE may have used
   preconfigured RA (CFRA) successfully.

### Reestablishment: rejected or looping

1. Find reestablishment request and response:
   ```bash
   grep -n "reestablishment" ue.log | grep "\[RRC\]" | head -10
   ```
2. If followed by `RRC setup` (not `RRC reestablishment`) → gNB rejected,
   forcing full re-attach. Likely the UE's context was released on the gNB side.
3. If no response at all → gNB did not respond; check gNB logs.

## Accumulated knowledge

<!-- Append new generalisable findings here as they are discovered. -->

- In CFRA (contention-free RA) handovers, the PRACH may not appear in ue.log
  because the gNB pre-assigns the preamble. The HO can still complete without
  visible PRACH lines.
- In inter-RU handovers with two RF ports, stdout.log shows the UE alternating
  between CL 00 and CL 01 RNTI assignments on each HO.
- `reconfigurationWithSync` containing a new `servingCellConfigCommon` block
  indicates a full cell change (including frequency/band change).
