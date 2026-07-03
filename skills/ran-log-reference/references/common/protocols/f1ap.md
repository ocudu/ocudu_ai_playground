# F1AP — semantics (CU ↔ DU, F1-C interface)

Artifact-agnostic meaning of the F1AP messages: what each procedure does, which
node initiates it, the UE identifiers it carries, and the common failure
signatures. **Observation is per-artifact** — each subtree documents how these
messages appear (tshark filters, gNB-log `Rx/Tx PDU` lines, UE markers). Spec:
TS 38.473 (see `../spec-map.md`).

F1AP carries the control plane between the gNB-CU and gNB-DU in a split
deployment: UE-context lifecycle, F1 infrastructure (F1 Setup, gNB-CU/DU
Configuration Update), and the RRC-container transfers between CU and DU.

## Procedures and codes

| Code | Procedure | Initiator | Meaning |
|---:|---|---|---|
|  1 | F1Setup | DU | F1 link establishment |
|  5 | UEContextSetup | CU | admit a new UE on the DU |
|  6 | UEContextRelease | CU | end a UE on the DU |
|  7 | UEContextModification | CU | bearer / cell change for a UE |
| 11 | InitialULRRCMessageTransfer | DU | first RRC message from a UE (post-RACH) |
| 12 | DLRRCMessageTransfer | CU | CU RRC → UE |
| 13 | ULRRCMessageTransfer | DU | UE RRC → CU |
| 26 | F1Removal | DU or CU | tear down the F1 interface |

## Identifiers carried

- `gNB-DU-UE-F1AP-ID` — DU-assigned, present from `InitialULRRCMessageTransfer`.
- `gNB-CU-UE-F1AP-ID` — CU-assigned, present once `UEContextSetupRequest` is sent.
- `C-RNTI` — carried in `InitialULRRCMessageTransfer` (the DU's C-RNTI for the UE).

Full identifier model (scope, stability across HO/reestablishment) in
`../identifiers.md`.

## UE arrival paths

A UE first appears on a DU via one of two paths — in a handover test the variation
across UEs is the *expected* signature, not an anomaly:

| First F1AP message | Meaning | DU role |
|---|---|---|
| `InitialULRRCMessageTransfer` (11) | UE attached via RACH on this cell; DU just allocated a C-RNTI, CU has not yet assigned a `gNB-CU-UE-F1AP-ID` | source / only DU |
| `UEContextSetup` (5) Request from CU | UE handed over to this DU under the same CU; no preceding RACH here, the C-RNTI in the request is fresh for the target cell | target DU |

## Failure signatures

- **UEContextSetupFailure** — DU can't accept the UE: no C-RNTI available, cell
  not admitting, or requested DRBs conflict.
- **UEContextReleaseCommand with `radio-connection-with-ue-lost`** — DU reported
  the UE lost; usually MAC inactivity timer or RLF.
- **No UEContextSetupResponse for a sent Request** — CU-side issue or DU crash.
- **InitialULRRCMessageTransfer without a following UEContextSetupRequest** — CU
  received the UE but isn't admitting it (CU-CP routing or AMF-selection issue).
- **InitialULRRCMessageTransfer with an empty DUtoCURRCContainer** — the DU could
  not allocate the UE's dedicated resources (commonly the cell PUCCH resource
  pool) and signals "can't serve this UE" per TS 38.473 §8.4.1.2. The CU then
  **rejects** the UE with a `UEContextReleaseCommand` carrying an `rrcReject` (with
  a wait timer) on `SRBID=0`. The IE is *present but zero-length*, so detect it by
  container **content length**, not presence.
