# Procedure: UE release

Expected-sequence reference. For an unexpected / stuck release, or release-phase
DL KO bursts, diagnose with `../troubleshooting/ue-release-issues.md`.

UE release happens when the AMF (or, in some configurations, the gNB itself
after the inactivity timer) decides the RRC connection should be torn down.
The trigger arrives as NGAP `UEContextReleaseCommand`, propagates down
through E1AP (bearer release) and F1AP (UE context release), and ends with
the DU clearing its UE state and the CU-CP acknowledging back to the AMF.

## Expected sequence

| Step | Layer | Log line |
|---|---|---|
| 1 | NGAP | `Rx PDU ... UEContextReleaseCommand` (carries `cause` IE) |
| 2 | RRC  | `DCCH DL rrcRelease` |
| 3 | CU-CP-E1 | `Tx PDU ... BearerContextReleaseCommand` |
| 4 | CU-UP-E1 | `Rx PDU ... BearerContextReleaseCommand` |
| 5 | CU-UP | `ue=N: Disconnecting PDU session with psi=N` |
| 6 | CU-UP-E1 | `Tx PDU ... BearerContextReleaseComplete` |
| 7 | CU-CP-E1 | `Rx PDU ... BearerContextReleaseComplete` |
| 8 | CU-CP-F1 | `Tx PDU ... UEContextReleaseCommand` |
| 9 | DU-F1 | `Rx PDU ... UEContextReleaseCommand` |
| 10 | DU-MNG | `ue=N: DRB traffic stopped` |
| 11 | DU-F1 | `proc="UE Context Release": RRC container not ACKed within a time window of 120msec.` *(common in simulated runs — the UE doesn't ack the DL because the test ends; benign)* |
| 12 | DU-MNG | `ue=N proc="UE Delete": Procedure started....` |
| 13 | DU-MNG | `ue=N: SRB and DRB traffic stopped` |
| 14 | DU-F1 | `ue=N c-rnti=0xNNNN ... F1 UE context removed.` |
| 15 | DU-MNG | `ue=N proc="UE Delete": Procedure finished successfully.` |
| 16 | DU-F1 | `Tx PDU ... UEContextReleaseComplete` |
| 17 | CU-CP-F1 | `Rx PDU ... UEContextReleaseComplete` |
| 18 | CU-CP | `ue=N: "UE Removal Routine" finished successfully` |
| 19 | NGAP | `Tx PDU ran_ue=N amf_ue=N: UEContextReleaseComplete` |

The un-ACKed RRCRelease at step 11 (plus any DL HARQs in flight at that instant)
is scored DTX→NACK and retransmitted through all RVs, so it shows up as a burst
of **DL KOs in the UE's final metrics interval**. This is the expected source of
DL-KO spikes when `ue_rem` events start in load / churn tests. It is a **UL
scheduling race, not the UE choosing to stop UL**: the RRCRelease is a polled
SRB1 RLC-AM PDU, and the UE's RLC STATUS needs a PUSCH grant to come back. Under
peak backlog the grant is too slow (large `max_sr_to_pusch_delay`, high
`nof_failed_uci_allocs`) so RLC hits max-retx and the context is removed
un-ACKed; the *same* release is cleanly ACKed once fewer UEs are pending — so the
failures cluster in the earliest releases. See `../troubleshooting/harq-ko-bler.md`
for the localize + load-dependence method.

After step 19 the AMF considers the UE released. The gNB context for `ue=N`
no longer exists; if the same UE re-attaches it will get a new `ue=N` index.

## Diagnosing failures

For failure markers (stuck release, context leak, inactivity trigger) and the
investigation checklist, see `../troubleshooting/ue-release-issues.md`.

## Cross-references

- `ue-attach.md` — release reverses the attach.
- `../troubleshooting/harq-ko-bler.md` — release-phase DL KO bursts.
- `pcap` type: `ngap.pcap` carries the `cause` IE in `UEContextReleaseCommand`.
