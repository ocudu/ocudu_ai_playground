# UE identifiers (artifact-agnostic model)

A single UE wears a different identifier in each protocol and each node. This is
the **definition** of each ID — who assigns it, its scope, and which procedures
change it. It is the same fact in every artifact; only the field/label used to
print it differs.

- The **per-artifact label** for each ID (tshark field, gNB log key, UE-log
  field) lives in that artifact's subtree.
- The **cross-artifact joining** (follow one UE across UE log ↔ gNB log ↔ pcaps,
  which ID to anchor on) is handled by the correlation layer.

## Identifier table

| Identifier | Assigned by | Scope | Survives HO? | Survives re-establishment? |
|---|---|---|---|---|
| C-RNTI | gNB scheduler (DU) | one cell, one UE-connection | No (target re-issues) | Usually no |
| `gNB-DU-UE-F1AP-ID` | DU | one DU, one UE | No (target DU re-issues) | Re-issued |
| `gNB-CU-UE-F1AP-ID` | CU | one CU, one UE | Yes (intra-CU HO) | Yes |
| `gNB-CU-CP-UE-E1AP-ID` | CU-CP | one E1 association | Yes | Yes |
| `gNB-CU-UP-UE-E1AP-ID` | CU-UP | one E1 association | Yes | Yes |
| `RAN-UE-NGAP-ID` | gNB | one NG association | Yes | Yes |
| `AMF-UE-NGAP-ID` | AMF | one AMF | Yes | Yes |

Tester-side anchors that are **stable for the whole run** (the natural join key
for correlating a tester log to a gNB context): the Amarisoft UEID (`ue.log`) and
the VIAVI `UE Id` (`*_Command_Log*.txt`).

## What each ID keys

- **C-RNTI** — the PHY/MAC radio key; together with SFN.slot it identifies a
  transmission on the air. Local to one cell; re-issued on HO and (usually)
  reestablishment. RNTIs are **recycled** within a run — disambiguate a reused
  RNTI by the surrounding event or time, never assume continuity.
- **F1AP UE IDs** — the CU↔DU pair for one UE on the F1 interface. The DU ID
  appears first (from the initial UL RRC transfer); the CU ID once the CU has sent
  UE Context Setup.
- **E1AP UE IDs** — the CU-CP↔CU-UP pair for one UE's bearer context. Second-most
  stable (survive intra-CU HO: the bearer is modified, not recreated).
- **NGAP UE IDs** — the gNB↔AMF pair. `RAN-UE-NGAP-ID` restarts at 1 when the gNB
  reconnects to the AMF; `AMF-UE-NGAP-ID` is the AMF's handle for the UE (and in
  these runs maps to the 5GC NAS UE ID).

## Time / run scope

Every ID above is local to a single NG/F1/E1 association and to **one run
directory**. Treat IDs as keys *within a run*; never assume continuity across
runs, and remember `RAN-UE-NGAP-ID` resets on gNB↔AMF reconnect.
