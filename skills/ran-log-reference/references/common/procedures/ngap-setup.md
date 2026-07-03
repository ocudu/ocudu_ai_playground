# Procedure: NG (NGAP) setup — abstract ladder

The artifact-agnostic gNB↔AMF association bring-up. The gNB's CU-CP connects to
the AMF over SCTP and exchanges NG Setup so it can serve UEs. This is the first
thing that must succeed in a run — nothing UE-related happens before it. Spec:
NGAP §8.7 / TS 38.413 (see `../spec-map.md`).

## Message ladder

| # | Message (abstract) | Between | Where seen |
|---:|---|---|---|
| 1 | SCTP association established (N2) | gNB ↔ AMF | gNB log (SCTP-GW / CU-CP) |
| 2 | NGSetupRequest (gNB PLMN/TAC/supported slices) | gNB → AMF | gNB log (NGAP), pcap `ngap` (21) |
| 3 | NGSetupResponse (AMF name, served GUAMIs, PLMN support) | AMF → gNB | gNB log (NGAP), pcap `ngap` (21) |

After step 3 the gNB is connected (log milestone `Connected to AMF. Supported
PLMNs: …`; stdout `==== gNB started ====`). An `NGSetupFailure` at step 3 means
PLMN/TAC/slice mismatch.

## Observation & diagnosis

How each step appears, and its per-step failure markers (SCTP connect failure,
NGSetupFailure cause, dropped association), live in the artifact subtrees — each
links back to this ladder. Protocol-level failure signatures:
`../protocols/ngap.md` § Failure signatures.
