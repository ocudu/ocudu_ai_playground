# Cross-correlation reference (the master model)

How to line up the *same* event across the Amarisoft UE log, the OCUDU gNB log,
and the packet captures. Per-artifact parsing detail lives in the per-type
subtrees (`../pcap/`, `../ocudu/`, `../amari-ue/`); this file is only about
joining sources.

## Timestamp formats per source

| Source | Format | Example | Clock |
|---|---|---|---|
| `gnb.log` | ISO-8601, microseconds | `2026-04-29T14:27:21.265863` | UTC (container) |
| `ue.log` / `mme.log` line | `HH:MM:SS.mmm` (no date) | `14:27:21.273` | UTC (container) |
| `ue.log` / `mme.log` header | `# Started on YYYY-MM-DD HH:MM:SS` | `# Started on 2026-04-29 14:27:19` | UTC anchor (prepend the date to line clocks) |
| pcap | `frame.time_epoch` (UTC seconds) | `1777472837.801640` | UTC seconds |
| VIAVI `*_Command_Log*.txt` | `DD/MM/YY HH:MM:SS:mmm` | `18/06/26 12:05:34:913` | **tester-local — may differ from the gNB host** |

## Clocks: do NOT assume a shared wall-clock — establish it per run

**A component and the pcaps it writes share one clock by construction** — the
same process emits `gnb.log` and `gnb_*.pcap`, so their Δ ≈ 0 always (the
log↔pcap check is a sanity / display-TZ guard, not a real offset risk). Verified:
`gnb.log` logs `NGSetupRequest` at `14:27:17.801593` and the first NGAP pcap frame
epoch is `1777472837.801640` = `14:27:17.801640` UTC — the **same instant**.
Co-located/NTP-synced UTC containers (e.g. OCUDU + an Amarisoft UE on one machine)
likewise align.

**But don't assume it across processes/hosts.** A separate tester/UE box, a remote
5GC, or any host on a different timezone or unsynced clock can be offset by
seconds to hours from the gNB. A VIAVI command log, in particular, carries
**tester-local** timestamps whose epoch may have nothing to do with the gNB's
(observed: a multi-hour offset, and a capture window that didn't even overlap the
gNB run in wall-clock terms).

So, per run:
1. **Prefer the clock-independent keys** below — PHY `(SFN.slot, RNTI)` and the
   RNTI / TC-RNTI chains — which join correctly regardless of clock relationship.
2. **Establish the offset empirically before trusting any wall-clock comparison**:
   match one unambiguous event across two sources (a unique RNTI/TC-RNTI, an NGAP
   setup) and measure Δ. Treat that Δ as the source-pair offset; don't assume 0.
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/correlate/align_clocks.py <run-dir>
   ```
3. Only after Δ is known (and small/explained) is direct wall-clock comparison
   between those two sources valid.

**Separate gotcha — display timezone:** even when sources do share UTC,
`capinfos`/`tshark` *display* frames in the host's local timezone (on a CEST host
the frame above prints as `16:27:17`). **Never compare a `capinfos`/`tshark` human
time to a log string** — use raw `frame.time_epoch` and treat container log
strings as UTC. `utils.epoch_to_utc()` converts epoch → UTC datetime correctly.

## The exact radio key: PHY (SFN.slot, RNTI)

The UE PHY and the gNB PHY log the **same** PUSCH/PUCCH/PDCCH/PDSCH at the
**same SFN.slot and RNTI**. This is the precise, clock-independent join key.
Verified: UE `66.4 ... 4601 PUSCH` ↔ gNB `[66.4] PUSCH: rnti=0x4601` (and the
1080 PUSCH of a single-UE run pair 1:1).

```
ue.log : 14:27:21.273 [PHY] UL 0035 00 4601  123.14 PUSCH: harq=0 ... tb_len=11 ...
gnb.log: 2026-04-29T14:27:21.281595 [PHY] [I] [  123.14] PUSCH: rnti=0x4601 ... tbs=11 crc=KO sinr=97.0dB
         ^ same slot 123.14, same rnti 4601 ; wall-clock +8.6 ms = gNB decode-log latency (NOT clock skew)
```

Notes and caveats:
- **RNTI printing differs**: UE prints bare hex (`4601`), gNB prints `0x4601`.
  Normalise with `utils.norm_rnti`.
- **SFN wraps every 1024 frames (~10.24 s)**, so an `SFN.slot` *string* recurs
  across a run. To pair correctly, disambiguate same-`(slot,rnti)` events by
  nearest wall-clock within a tolerance well below one wrap (`correlate_radio.py`
  uses 0.5 s). Never join on the slot string alone over a multi-wrap run.
- **MAC/SCHED lag**: UL events (PRACH/PUSCH/PUCCH) are *processed* several slots
  after the PHY transmission, so a MAC/SCHED line's own slot is later than the
  PHY TX slot. Join MAC/SCHED→PHY via the **`slot_rx=`** field when the build
  emits it (it gives the true PHY reception slot); otherwise join on
  `(SFN.slot, RNTI)` at the PHY layer or calibrate the processing-delay offset.
  (`slot_rx=` is build/verbosity-dependent and absent in the default-config
  example runs.)
- **PRACH is the exception**: the UE prints `sequence_index=` and the gNB prints
  `idx=` — **different numbering**, so do *not* match PRACH on the raw index.
  Correlate PRACH via the resulting **tc-rnti** and the subsequent **Msg3 PUSCH**
  (which has a clean `(SFN.slot, RNTI)` join), or by wall-clock occasion.

## Matching-key priority

1. **PHY `(SFN.slot, RNTI)`** — exact, for PUSCH/PUCCH/PDCCH/PDSCH.
2. **RNTI / TC-RNTI / preamble→tc-rnti chain / TBS / PRB** — to disambiguate UEs
   sharing a slot (RACH contention) and to bridge PRACH→Msg3.
3. **Wall-clock window** — cross-check, and the primary key for non-PHY
   artifacts (pcap NGAP/F1AP/E1AP, 5GC `mme.log`, VIAVI). Valid **only after** the
   source-pair clock offset is known to be ~0 or has been measured (§ Clocks);
   never assume a shared clock for an off-host source.

## Cross-source signals only this layer can see

- **Side attribution**: gNB `PUSCH crc=KO` *with* a matching UE TX at the same
  `(slot,rnti)` ⇒ the UE *did* transmit → gNB-side decode / ZMQ-sample issue,
  **not** a UE DTX. gNB `crc=KO sinr=inf` *without* a UE TX ⇒ true DTX.
  (`correlate_radio.py` labels these `rx-ko/ue-tx` vs `rx-ko/ue-silent`.)
- **RACH contention**: two UE PUSCH at the same `(slot, tc-rnti)` from different
  UEIDs, one gNB event → collision (`ue-extra-tx/contention`); expected in
  multi-UE attach, not a fault.
- **Count reconciliation**: UE-side attaches vs gNB `UE created` vs NGAP
  `InitialUEMessage` vs pcap — disagreement localises where UEs are lost.

## Scripts

| Script | Purpose |
|---|---|
| `resolve.py` | Components, artifacts, testbed map, clock anchors (the `correlate` resolver) |
| `align_clocks.py` | Measure the log↔pcap / UE↔gNB clock offset (don't assume 0) + PHY slot alignment; report decode latency vs genuine clock skew |
| `correlate_radio.py` | Join UE↔gNB PHY events on `(SFN.slot, RNTI)`; flag rx-ko/missing/contention; DTX vs degradation |
| `map_ue_ids.py` | Per-pcap UE-identifier lifecycle (f1ap/ngap/e1ap); feeds `ue-identity-map.md` |
