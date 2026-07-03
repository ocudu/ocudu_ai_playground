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

## Observation surfaces (per artifact)

- **gNB log (`ocudu`)** — `../../ocudu/reference/ngap-setup.md`: the SCTP + NGAP
  log-line sequence and stdout milestones.
- **pcap** — analyze `ngap.pcap` with the `pcap` type; NGSetup is NGAP code 21
  (`../../pcap/protocols/ngap.md`).

## Diagnosing failures

gNB-side in `../../ocudu/troubleshooting/ngap-amf-connection.md` (SCTP connect
failure, NGSetupFailure cause, dropped association). Protocol signatures:
`../protocols/ngap.md` § Failure signatures.
