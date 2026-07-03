# Procedure: UE starvation in fallback mode

Use this when UEs enter fallback (post-RACH, pre-RRC-config) and their
SRB0/SRB1/ConRes traffic drains too slowly or not at all — regardless of the
downstream symptom. Common surface symptoms:

- `[SCHED ][W] ... ra-ContentionResolutionTimer ... expired ... before ConRes CE
  was scheduled. UE will stop being scheduled`
- `[RRC ][W] ... "RRC Setup Procedure" timed out` / `"RRC Reestablishment ..." timed out`
- UEs that reached `MAC UE Creation: finished successfully` but never get a Msg4
  / RRCSetup DL grant.
- `metrics.json` / `[METRICS]` row `conres_timer_expired > 0`.

All of these share one root question: **why did the `ue_fallback_scheduler` not
get this UE's grant out in time?** The fallback scheduler owns DL SRB0/SRB1 +
ConRes CE and UL SRB1 for UEs still in fallback; it allocates on the **RA /
common search space** (`ra_search_space_id`, typically `ss_id=1`) using DCI 1_0
scrambled with TC-RNTI (ConRes/Msg4) or C-RNTI.

## Boundary vs. attach failure

This is the scheduler-resource playbook for when fallback grants (ConRes CE,
Msg4/SRB0, SRB1) never get **scheduled** — it applies to attach, reestablishment,
and F1AP-created UEs alike. It is *not* the general attach-failure doc: if Msg4
**was** scheduled and ACKed but the UE never sent `rrcSetupComplete` (a UE-side or
SRB1-UL problem), or the attach broke at PRACH/NGAP/security/ICS, go to
`ue-attach-failure.md`. The dividing line for a missing `rrcSetupComplete` is
whether a `CON_RES` DL PDU / Msg4 grant was ever emitted: **never emitted →
here**; **emitted but unanswered → `ue-attach-failure.md`**.

## Key: the symptom layer is usually not the bottleneck layer

The failure shows up on DL (no Msg4 / no ConRes), so the reflex is to look at DL
fallback resources. But the fallback DL search space is frequently found **idle**
while the UE starves — that idleness is the tell that the block is *elsewhere*
(the UL ACK resource, an attempt-budget stop, or a state gate), not DL
contention. Measure utilization first; do not assume.

## Relevant code invariants (mainline)

Generalisable facts about `lib/scheduler/ue_scheduling/ue_fallback_scheduler.cpp`
that drive attribution (constants may be re-tuned; verify against the run's
build commit):

- **Run order per slot** (`run_slot`): DL retx → UL new/retx → DL new-tx
  `conres_only` → `srb0` → `srb1`. A shared per-slot attempt counter
  (`max_dl_sched_attempts`, impl-defined ~22) spans **all** of these; when it is
  hit, `stop_dl_scheduling` aborts the rest of DL for that slot. Its own comment
  notes it only guarantees ~1 fallback UE allocated per TDD period.
- **The fallback scheduler runs before the slice/dedicated scheduler**
  (`ue_scheduler_impl.cpp`), but that only protects the **current** DL slot's
  grid. A HARQ-ACK PUCCH or PUSCH is booked on a **future** UL slot that the
  dedicated scheduler already filled in earlier slot iterations — per-slot
  ordering does not win that cross-slot race.
- **ConRes/Msg4 ACK uses common PUCCH and needs a fully-UL slot.** For a UE whose
  dedicated config is not yet confirmed, the ACK goes on common PUCCH
  (`alloc_common_harq_ack`) and `allocate_ue_fallback_pucch` only accepts a slot
  where `is_fully_ul_enabled` is true — a TDD *special* slot's UL symbols do not
  count.
- **Fallback k1 is capped**: candidates are `[min_k1 .. 7]` (`dci_1_0_k1_values`).
  The dedicated scheduler has no such cap and uses much larger k1. So a fallback
  UE can only reach full-UL slots that lie within 7 slots, using specific k1s,
  while dedicated ACKs reach (and pre-fill) those same UL slots from further back.
- **Timer**: `ra-ContentionResolutionTimer` (`ra_con_res_timer`, in subframes) is
  measured from `msg3_rx_slot`; on expiry `handle_conres_expiry` deactivates the
  UE.

## Candidate root causes → the signal that attributes each

| Candidate cause | Confirming signal |
|---|---|
| **UL ACK-slot funneling** — UL-scarce TDD (few `nof_ul_slots`) + a high `min_k1`/`min_k2` floor forces all HARQ-ACK/PUSCH onto one slot position; that slot's PUCCH/RBs (incl. the band-edge common-PUCCH region) deplete, so the ConRes common PUCCH cannot be placed | Fallback DL search space idle while DL grid has room; PUCCH+PUSCH occupancy concentrated on one slot-position-mod-period; special slot's UL symbols unused; fallback grants absent from DL positions whose `[min_k1..7]` window reaches no full-UL slot |
| **Bursty simultaneous RACH** — many UEs on the same PRACH occasion enter fallback together and exceed the ~1-UE/period fallback throughput | `msg3 rx at slot=X` clustering (multiple UEs same slot); `conres_timer_expired` arrives in bursts aligned to those slots |
| **Attempt-budget / failure storm** — `max_dl_sched_attempts` exhausted by retx or repeated failed allocs → `stop_dl_scheduling` before ConRes pass | Non-trivial fallback DL **retx** volume (`newtx=false` on the RA search space); or successes ≈1/slot then nothing (budget hit) |
| **DL common PDCCH/PDSCH contention** — CORESET0 / common SS crowded | `failed_common_dl_pdcch > 0` in metrics (if `0`, DL common PDCCH is *not* the cause); DL grid genuinely full on the fallback slots |
| **ConRes/C-RNTI CE never pending** — state gate (F1AP-created vs UL-CCCH UE; C-RNTI CE vs UE-ConRes-ID CE) | UE never appears in any RA-search-space DL grant and no `conres` scheduling attempt; check the pcell conres state / `is_con_res_id_pending` path |

## Investigation checklist

1. **Utilization first.** Is the RA/common search space actually busy? If DL has
   free capacity but fallback grants are sparse, this is *not* DL contention —
   pivot to the UL/ACK and budget causes.
   ```bash
   # DL grants by search space (ss_id of the RA search space vs dedicated)
   grep -oE "DL: [^,]*ss_id=[0-9]+" gnb.log | grep -oE "ss_id=[0-9]+" | sort | uniq -c
   ```
2. **Rule out DL common PDCCH / retx.** Check `failed_common_dl_pdcch` in
   `[METRICS]`; count fallback retx on the RA SS:
   ```bash
   grep -oE "DL: [^,]*ss_id=<RA_SS> [^,]*newtx=(true|false)" gnb.log \
     | grep -oE "newtx=(true|false)" | sort | uniq -c
   ```
3. **UL funneling — the decisive histograms.** Bucket by slot-position modulo the
   TDD period (`dl_ul_tx_period`). If all PUCCH/PUSCH sit on one position and
   fallback grants avoid whole DL positions, the `min_k1`/`min_k2` floor ×
   UL-scarce TDD is funneling the ACK resource. Set `PERIOD` and `RA_SS`:
   ```bash
   python3 - gnb.log <<'PY'
   import re,sys
   from collections import Counter
   PERIOD=5; RA_SS='1'          # dl_ul_tx_period; RA search-space id
   pucch=Counter(); pos_k1=Counter()
   for ln in open(sys.argv[1],errors='replace'):
       if 'Slot decisions' not in ln: continue
       m=re.search(r'\[\s*\d+\.(\d+)\].*?\(\d+ PDSCHs, \d+ PUSCHs, (\d+) PUCCHs\)',ln)
       if m: pucch[int(m.group(1))%PERIOD]+=int(m.group(2))
       p=re.search(r'\[\s*\d+\.(\d+)\]',ln); pos=int(p.group(1))%PERIOD if p else -1
       for g in re.findall(rf'DL: [^,]*ss_id={RA_SS}[^,]*',ln):
           k=re.search(r'k1=(\d+)',g); pos_k1[(pos,k.group(1) if k else '?')]+=1
   print("PUCCHs summed by slot-pos mod period:", dict(sorted(pucch.items())))
   print("fallback DL grants by (slot-pos, k1):")
   for k in sorted(pos_k1): print(" ",k,pos_k1[k])
   PY
   ```
   Cross-check the TDD layout in `ocudu_gnb.yml` (`tdd_ul_dl_cfg`:
   `dl_ul_tx_period`, `nof_dl_slots`, `nof_ul_slots`, `nof_dl_symbols`,
   `nof_ul_symbols`) and the `min_k1`/`min_k2` in effect. A DL position `p` can
   host a fallback ConRes only if some `k1∈[min_k1..7]` makes `(p+k1) mod period`
   a fully-UL slot.
4. **Dedicated k1/k2 spread.** High dedicated k1 (well past 7) means dedicated
   ACKs pre-book the sparse UL slots from many prior slots, ahead of the
   fallback scheduler's reach:
   ```bash
   grep -oE "DL: [^,]*ss_id=<DED_SS>[^,]*k1=[0-9]+" gnb.log \
     | grep -oE "k1=[0-9]+" | sort | uniq -c
   ```
5. **Burstiness.** `grep -oE "msg3 rx at slot=[0-9.]+" gnb.log | sort | uniq -c`
   — several UEs sharing one Msg3 slot that all expire together points at
   throughput vs. arrival rate, not a single UE's bad luck.

## Mitigation directions (report, don't apply)

- **Lower `min_k1`/`min_k2`** so nearer UL opportunities (and a special slot's UL
  symbols, for short PUCCH/PUSCH formats) can be used — un-funnels the one UL
  slot, unlocks DL positions the fallback scheduler otherwise cannot ACK from,
  and shortens ACK latency.
- **Widen UL** (TDD ratio / `nof_ul_slots`) or the common-PUCCH resource pool —
  the root scarcity is UL when the funnel signal is present.
- **Scheduler** (code): don't let a PUCCH-side (UL) allocation failure consume the
  DL attempt budget / abort the ConRes pass; prioritise ConRes over other UEs'
  retx/SRB1.

## Cross-references

- `throughput-degradation.md` — steady-state DL/UL throughput and late HARQs.
- `../reference/ue-attach.md` — expected attach/ConRes/Msg4 sequence.
- `../reference/reestablishment.md` — reestablishment uses C-RNTI-based contention.
- `ue-attach-failure.md` — attach broke somewhere other than fallback scheduling.
- Correlate with the UE side (`amari-ue` type) to confirm the UE actually
  transmitted Msg3 / listened for Msg4.
</content>
</invoke>
