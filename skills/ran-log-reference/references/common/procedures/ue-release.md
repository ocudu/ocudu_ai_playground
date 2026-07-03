# Procedure: UE release — abstract ladder

The artifact-agnostic teardown sequence for a UE's RRC connection. Triggered when
the AMF (or the gNB itself after the inactivity timer) decides the connection
should end: an NGAP `UEContextReleaseCommand` propagates down through E1AP (bearer
release) and F1AP (UE-context release), the DU clears its UE state, and the CU-CP
acknowledges to the AMF. Spec: NGAP §8.3.3 / F1AP §8.3.3 (see `../spec-map.md`).

## Message ladder

| # | Message (abstract) | Between | Where seen |
|---:|---|---|---|
| 1 | UEContextReleaseCommand (carries the `cause` IE) | AMF → gNB | gNB log (NGAP), pcap `ngap` (41) |
| 2 | RRC Release (`rrcRelease`) | gNB → UE | UE log (RRC), gNB log (RRC) |
| 3 | BearerContextReleaseCommand / Complete | CU-CP ↔ CU-UP | gNB log (E1), pcap `e1ap` (11) |
| 4 | UEContextReleaseCommand / Complete | CU ↔ DU | gNB log (F1), pcap `f1ap` (6) |
| 5 | UEContextReleaseComplete | gNB → AMF | gNB log (NGAP), pcap `ngap` (41) |

For a **gNB-initiated** release (RLF), an NGAP `UEContextReleaseRequest` (code 42,
cause `radio-connection-with-ue-lost`) precedes step 1; the AMF then echoes the
Command. After step 5 the gNB context is gone — a re-attaching UE gets a fresh
`ue=` index.

## Cause-IE values

| Cause | Meaning |
|---|---|
| `radio-connection-with-ue-lost` | gNB lost the UE (RLF) |
| `user-inactivity` | inactivity timer expired (normal idle) — not a failure |
| `release-due-to-cn-detected-mobility` | AMF detected the UE moved out |
| `release-due-to-pre-emption` | resource pre-emption by higher-priority traffic |
| `unspecified` | generic; read the surrounding events |

## Observation surfaces (per artifact)

- **gNB log (`ocudu`)** — `../../ocudu/reference/ue-release.md`: the per-layer
  E1/F1 sequence, plus the un-ACKed RRCRelease → DL-KO-burst effect in load runs.
- **pcap** — `../../pcap/procedures/ue-context-release.md`: gNB- vs AMF-initiated
  sequences, cause-IE values, and tshark filters.

## Diagnosing failures

gNB-side in `../../ocudu/troubleshooting/ue-release-issues.md` (stuck release,
context leak) and `../../ocudu/troubleshooting/harq-ko-bler.md` (release-phase DL
KO bursts); pcap-side in `../../pcap/procedures/ue-context-release.md`
§ Failure markers. Protocol signatures: `../protocols/ngap.md`.
