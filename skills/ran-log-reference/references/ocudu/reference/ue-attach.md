# Procedure: UE attach (RRC connection + Initial Context Setup)

gNB-log observation surface. The artifact-agnostic message ladder (what should
happen, across all artifacts) is `../../common/procedures/ue-attach.md`; this file
maps that ladder to the OCUDU `gnb.log` lines. For diagnosing a *failed* attach,
see `../troubleshooting/ue-attach-failure.md`.

## Expected sequence (single UE, log levels at info)

| Step | Layer | Log line |
|---|---|---|
| 1 | SCHED | `Processed slot events pci=N: prach(ra-rnti=0xN preamble=N tc-rnti=0xNNNN)` |
| 2 | SCHED | `Slot decisions pci=N ...: RAR: ra-rnti=0xN rb=[..] tbs=N` (MSG2) |
| 3 | SCHED | `Slot decisions pci=N ...: UL: ue=8192 rnti=0xNNNN ... msg3_delay=N` (MSG3 grant) |
| 4 | MAC | `UL rnti=0xNNNN subPDUs: [CCCH48: len=6, ...]` (MSG3 decoded) |
| 5 | MAC | `proc="MAC UE Creation": finished successfully` |
| 6 | MAC | `DL PDU: ue=N rnti=0xNNNN size=N: CON_RES: id=...` (MSG4 contention resolution) |
| 7 | CU-CP-F1 | `Rx PDU du=0 tid=N du_ue=N: InitialULRRCMessageTransfer` |
| 8 | CU-CP | `ue=N c-rnti=0xNNNN: UE created` |
| 9 | RRC | `CCCH UL rrcSetupRequest` |
| 10 | RRC | `CCCH DL rrcSetup` |
| 11 | RRC | `DCCH UL rrcSetupComplete` |
| 12 | NGAP | `Tx PDU ue=N ran_ue=N: InitialUEMessage` (carries NAS Registration Request) |
| 13 | NGAP | `Rx PDU ue=N ran_ue=N amf_ue=N: DownlinkNASTransport` (NAS Authentication Request) |
| 14 | RRC | `DCCH DL dlInformationTransfer` / `DCCH UL ulInformationTransfer` (NAS exchanges) |
| 15 | NGAP | `Rx PDU ... amf_ue=N: InitialContextSetupRequest` |
| 16 | CU-CP | `ue=N: "Initial Context Setup Routine" initialized` |
| 17 | SEC  | `K_gNB: ...` and derived RRC/UP keys (often blank when `hex_max_size: 0`) |
| 18 | RRC  | `DCCH DL securityModeCommand` |
| 19 | CU-CP-F1 | `Tx PDU ... UEContextSetupRequest` |
| 20 | DU-F1 | `Rx PDU ... UEContextSetupRequest` |
| 21 | DU-F1 | `Tx PDU ... UEContextSetupResponse` |
| 22 | RRC  | `DCCH UL securityModeComplete` |
| 23 | RRC  | `DCCH DL ueCapabilityEnquiry` |
| 24 | RRC  | `DCCH UL ueCapabilityInformation` |
| 25 | CU-CP-E1 | `Tx PDU ... BearerContextSetupRequest` |
| 26 | CU-UP-E1 | `Tx PDU ... BearerContextSetupResponse` |
| 27 | CU-CP-E1 | `Tx PDU ... BearerContextModificationRequest` (feeds the DU's F1-U DL TEIDs to CU-UP, before the reconfiguration — full E1/F1 DRB exchange in `pdu-session-setup.md`) |
| 28 | RRC  | `DCCH DL rrcReconfiguration` (carries DRB config) |
| 29 | RRC  | `DCCH UL rrcReconfigurationComplete` |
| 30 | CU-CP | `ue=N: "Initial Context Setup Routine" finished successfully` |
| 31 | NGAP | `Tx PDU ... InitialContextSetupResponse` |

After step 31 the UE is fully attached and DRBs are operational. The gNB's
`[GTPU]` lines start showing UL/DL SDUs flowing.

## Diagnosing failures

For failure markers (which step is missing → likely cause), the investigation
checklist, and multi-UE `Initial Context Setup OK K/N` gap analysis, see
`../troubleshooting/ue-attach-failure.md`. A missing MSG4/ConRes (step 6) is a
fallback-scheduling problem → `../troubleshooting/ue-fallback-scheduling-issues.md`.

## Cross-references

- `pdu-session-setup.md` — the DRB/bearer setup that overlaps steps 25–29.
- `../troubleshooting/ue-attach-failure.md` — attach failure dispatch.
</content>
