# common — artifact-agnostic reference

Protocol/procedure **semantics** and standards material that hold regardless of
which artifact you are looking at. The F1AP message set, the UE-attach message
ladder, and the UE identifier model are the same facts whether observed in a gNB
log, a UE log, or a pcap — only the *observation surface* differs. This subtree
carries that shared layer so the per-type subtrees don't each restate it.

The three axes, and where each lives:

| Axis | Question | Where |
|---|---|---|
| **Semantics** | What *should* happen, per the standard? | **`common/`** (here) |
| **Observation** | How does it *look* in this artifact? | `ocudu/`, `amari-ue/`, `pcap/`, `viavi/` |
| **Alignment** | How do I line up several artifacts' observations? | `correlate/` |

**How to use it:** `resolve.py` never selects `common/` — it is loaded *in
addition* to a type subtree (or `correlate/`) when you need the protocol/procedure
meaning behind an observation, an identifier definition, a 3GPP clause, or a FAPI
message. A per-type doc points here for the shared semantics and keeps only its
own log-line / tshark / UE-marker detail.

## Contents

- **`identifiers.md`** — the UE identity model: C-RNTI and the F1AP / E1AP / NGAP
  / AMF IDs — definitions, assigning node, scope, and which survive HO /
  reestablishment / release. The per-artifact field names live in each subtree;
  the cross-artifact *joining* is handled by the correlation layer.
- **`spec-map.md`** — procedure/message → governing 3GPP TS + clause, and how to
  hand off to the `spec-explorer` skill for canonical text.
- **`fapi.md`** — the SCF FAPI (MAC↔PHY) message reference.
- **`protocols/`** — per-protocol message semantics (procedure codes, IE/identifier
  meaning), artifact-agnostic. Currently: `f1ap.md`, `e1ap.md`, `ngap.md`.
  (MAC-NR/RLC-NR live only in the `pcap` subtree — no cross-artifact duplication
  to lift, so they stay there as pcap dissection.)
- **`procedures/`** — abstract cross-layer procedure ladders with a per-artifact
  "where seen" column: `ue-attach.md`, `pdu-session-setup.md`, `handover.md`,
  `reestablishment.md`, `ue-release.md`, `random-access.md`, `ngap-setup.md`.

Coverage is incremental: protocols and procedures move here as they are needed;
the per-type subtrees remain authoritative for anything not yet migrated.
