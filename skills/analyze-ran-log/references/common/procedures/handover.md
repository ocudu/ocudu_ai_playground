# Procedure: Handover — abstract ladder

The artifact-agnostic handover sequences. The HO command always reaches the UE as
an `rrcReconfiguration` carrying `reconfigurationWithSync` (target PCI, RACH
config, security key chain); what differs across variants is the network-side
signalling that precedes it. Spec: TS 38.300 §9.2.3, F1AP/NGAP/XnAP §8.4 (see
`../spec-map.md`).

## Variants

| Variant | Preceding signalling | Trigger message |
|---|---|---|
| Intra-CU intra-DU (target cell change only) | F1AP UEContextModification on the one DU | UEContextModificationRequest (RRC reconfig) |
| Intra-CU inter-DU (source DU → target DU, one CU) | F1AP UEContextSetup on the target DU | UEContextSetupRequest (target) |
| Inter-CU / N2 (source gNB → target gNB via AMF) | NGAP HandoverPreparation | HandoverRequired (NGAP code 12) |

## Message ladder — intra-CU inter-DU with CFRA (representative)

| # | Message (abstract) | Between | Where seen |
|---:|---|---|---|
| 1 | UEContextModificationRequest (HO prep on source DU) | CU → source DU | gNB log (F1), pcap `f1ap` (7, src DU) |
| 2 | UEContextSetupRequest / Response (target DU admits UE, fresh C-RNTI) | CU ↔ target DU | gNB log (F1), pcap `f1ap` (5, tgt DU) |
| 3 | RRC Reconfiguration w/ reconfigurationWithSync (HO command) | gNB → UE | UE log (RRC), gNB log (RRC), pcap `f1ap` (12) |
| 4 | PRACH on target (CFRA preamble) → RAR | UE ↔ target cell | gNB log (SCHED), UE log (PHY), pcap `mac` (RAR) |
| 5 | RRC ReconfigurationComplete (on the target cell) | UE → gNB | UE log (RRC, target CL), gNB log (RRC), pcap `f1ap` (13) |
| 6 | UEContextReleaseCommand / Complete (source DU) | CU ↔ source DU | gNB log (F1), pcap `f1ap` (6, src DU) |

Inter-CU adds NGAP `HandoverRequired` → `HandoverCommand` (steps before 3) and
`Up/DownlinkRANStatusTransfer`; a `HandoverFailure` (NGAP) means the target
rejected. Intra-DU omits steps 2 and 6 (no DU change).

Key tells: the `ReconfigurationComplete` is sent on the **target** cell (different
cell index / fresh C-RNTI than the command); a reconfiguration **without**
`reconfigurationWithSync` is a bearer/measurement update, not a HO.

## Observation & diagnosis

How each step appears, and its per-step failure markers, live in the artifact
subtrees — each links back to this ladder. Protocol-level failure signatures:
`../protocols/f1ap.md`, `../protocols/ngap.md`. A failed HO usually surfaces as a
re-establishment → `reestablishment.md`.
