# Procedure: DL / UL HARQ KOs (BLER)

> Outcome vocabulary (ACK / NACK / DTX, and how detection status maps to them):
> [`uci.md`](../reference/uci.md).

A "KO" is a HARQ transport block the gNB did not count as delivered. **DL and UL
KOs are detected differently — keep them separate:**

- **DL KO** (`dl_nof_nok`): no positive HARQ-ACK for a PDSCH — but this lumps a
  real **NACK** (UE decoded the TB wrong) together with a **DTX** scored as a NACK
  (UE ACKed, gNB missed/garbled the UCI), so a DL KO is **not** necessarily lost
  data. Telling the two apart (via the `*_invalid_harqs` counters) is
  `../reference/uci.md` vocabulary — pin it down early.
- **UL KO** (`ul_nof_nok`): the gNB failed to decode the PUSCH (`crc=KO`) —
  observed directly, so no DTX ambiguity.

The counters live in **two** places (same values): `metrics.json`
(`ue_list[].dl_nof_nok` / `ul_nof_nok` vs `dl_nof_ok` / `ul_nof_ok`), **and** the
per-UE scheduler lines in `gnb.log`
(`[METRICS] Scheduler UE ue=N ... dl_nof_ok=.. dl_nof_nok=.. dl_error_rate=..% ... ul_nof_ok=.. ul_nof_nok=.. ul_error_rate=..%`).
BLER = `nok / (ok + nok)`. Work the **ratio and its location**, not the absolute
count — "a lot of KOs" is only a fault when the ratio is high in a regime where
it should be near zero.

## Check the channel regime first — perfect vs. real

This sets the baseline BLER to expect and gates how you read everything below. In
an ideal channel (ZMQ / RF simulator, no fading) first transmissions should
nearly always decode, so BLER should be ~0 across the whole lifecycle — any KO
cluster then points at mechanics (scheduler / teardown), not the radio. In a
**real / noisy** channel there is a roughly constant baseline NOK rate
everywhere, so the localization below must be read *against* that baseline — only
KOs beyond it are a signal, and a flat nonzero BLER is expected, not a fault.
Establish the regime first:

- `ocudu_gnb.yml` → `ru_sdr.device_driver: zmq` (see `../reference/config-format.md`), and the
  run is driven by an `amarisoft-ue-*` or viavi with no channel model.
- PUSCH/PUCCH `sinr` in the PHY lines sits very high and flat (tens of dB).

In a perfect channel, KOs are almost never a link problem — look at scheduler /
teardown mechanics, not MCS or coverage.

## Localize the KOs — attach / steady-state / release

With the baseline established, where in the UE lifecycle the KOs cluster *above*
it points straight at the cause. Bucket each KO interval into attach /
steady-state / release by lining per-UE `dl_nof_nok` / `ul_nof_nok` (the
`[METRICS] Scheduler UE` lines or `metrics.json` intervals) up against the
`ue_create` / `ue_rem` events (cell `event_list`, or the summary script).

| Where KOs cluster | Likely cause | Where to look |
|---|---|---|
| **Attach** (just after `ue_create` / Msg4) | Msg4 / contention, CSI not yet valid, RA collisions | `../reference/ue-attach.md`, `msg3_nok`, PRACH |
| **Steady state** | Real link (only if channel is noisy) or overload; in a perfect channel should be ~0 — if not, suspect a scheduler / HARQ bug | § Check the channel regime first; `throughput-degradation.md` |
| **Release** (just before `ue_rem`) | Teardown feedback race: the RRCRelease (SRB1) and in-flight DL HARQs need UL feedback (RLC STATUS / HARQ-ACK), but under heavy UL load the UE may not get a PUSCH grant in time → release goes un-ACKed, DL HARQs retransmit through all RVs then force-removed, each a KO | `../reference/ue-release.md`; § Release-phase KOs in depth |

## Common misattributions — rule these out

- **OLLA is not the explanation in a perfect channel.** Outer-loop link
  adaptation targets a small nonzero BLER (scheduler defaults
  `olla_dl_target_bler` / `olla_ul_target_bler` = 0.01), but with a perfect
  channel and stable CQI it induces essentially no KOs. Only invoke the
  OLLA-target argument when the channel is genuinely noisy and BLER is hovering
  near the configured target.
- **`nof_failed_uci_allocs` does NOT create DL KOs.** If the scheduler cannot
  allocate the PUCCH/PUSCH resource for a PDSCH's HARQ-ACK (UCI), it does **not**
  allocate the PDCCH/PDSCH either — the DL grant is skipped entirely. So a high
  `nof_failed_uci_allocs` (cell metric) means *suppressed* DL grants → lower
  throughput, never PDSCHs left unacknowledged. Rule it out as a KO cause; it
  belongs to `throughput-degradation.md`.

## Release-phase KOs in depth

The release bucket is the common one in load / churn tests: KOs are ~0 through
attach and steady state and spike when `ue_rem` events begin. The crucial tell
is that it is **load-dependent, not intrinsic** — the *same* RRCRelease that goes
un-ACKed under peak backlog is cleanly ACKed once fewer UEs are pending. Do
**not** conclude "the UE stops UL on release"; the UE would ACK if scheduled in
time. The real bottleneck is the **UL scheduler** (correlates with high
`nof_failed_uci_allocs` and large `max_sr_to_pusch_delay`), not the radio link.
How to see it:

- Per-UE signal: the releasing UE's PUCCH shows `metric≈0`, deeply negative
  `sinr`, DTX HARQ codes, and the scheduler retransmits its stuck DL HARQs (`rv`
  cycling 0→2→3→1…) until context removal (`f0f1_invalid_harqs` climbs alongside
  `dl_nof_nok` in that UE's final interval). This is the *symptom* of missing UL
  feedback, not proof the UE went silent by choice.
- RLC confirmation (rlc.pcap, enable the `rlc_nr_udp` heuristic — see
  `../../pcap/protocols/rlc.md`): the RRCRelease is an SRB1 RLC-AM PDU with the
  Poll bit set. A clean release = a single transmission plus a UL STATUS PDU
  whose `ACK_SN` advances past it, ~tens of ms later. A failed one = the same PDU
  poll-retransmitted with **no** STATUS ever, because the UE's STATUS can't get a
  PUSCH grant before RLC max-retx / context removal.
- Load-dependence check (the decisive one): tabulate, per released UE, whether
  its RRCRelease was RLC-ACKed vs its release order/time. Failures cluster in the
  *earliest* releases (peak backlog) and disappear once the backlog drains; ack
  delay shrinks as UEs leave. That pattern *is* the "PUSCH not scheduled fast
  enough" diagnosis.

This is expected under load, not a link/PHY fault. Confirm the trigger in the
F1AP pcap (`UEContextReleaseCommand` carrying `rrcRelease`) with
`scripts/pcap/f1ap_messages.py`.
