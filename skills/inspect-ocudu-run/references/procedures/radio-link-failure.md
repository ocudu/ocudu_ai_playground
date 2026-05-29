# Radio link failure (cross-artifact triage)

When a UE drops or reestablishes, the central question is **which side failed**:
did the UE stop transmitting (DTX), did the channel degrade, or did the gNB fail
to decode a transmission the UE actually sent? Only cross-correlation answers
this — `gnb.log` alone cannot tell a UE DTX from a gNB decode miss.

## Step 1 — locate the failure window

Get the RNTI and the approximate time from the symptom (or from
`analyze-ocudu-gnb-log` flagging an RLF / reestablishment). The gNB MAC logs the
RLF cause (e.g. `RLF detected. Cause: 100 consecutive HARQ-ACK KOs`).

## Step 2 — classify the UL failure across sources

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/correlate_radio.py <run-dir> --kind pusch --rnti 0x<RNTI>
```

Read the status of the slots leading into the failure:

| `correlate_radio` status | Meaning | Implication |
|---|---|---|
| `rx-ok` then stops | UE stopped transmitting cleanly | UE went idle / released elsewhere |
| `rx-ko/ue-silent` (gNB `crc=KO sinr=inf`, no UE TX) | **DTX** — UE sent nothing | UE-side: lost DL (no grant decoded), or UE RLF first |
| `rx-ko/ue-tx` (gNB `crc=KO`, UE DID transmit) | gNB couldn't decode a real TX | gNB-side decode / channel / ZMQ-sample misalignment — NOT a UE DTX |
| `gnb-missing` (UE TX, no gNB event) | gNB PHY never saw the grant/transmission | scheduling / RU / fronthaul |

This `rx-ko/ue-tx` vs `rx-ko/ue-silent` split is the key cross-source verdict.

## Step 3 — if DTX, look at the DL toward the UE

A UE goes silent when it stops receiving DL grants (PDCCH). Delegate to
`analyze-amari-ue-log` to inspect the UE's PDCCH decoding around the window
(e.g. spurious search-space / `ss_id` mismatches in ZMQ), and to
`analyze-ocudu-gnb-log` for the DL scheduling the gNB believed it sent. Correlate
PDCCH/PDSCH on `(SFN.slot, RNTI)`:
```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/correlate_radio.py <run-dir> --kind pdcch --rnti 0x<RNTI>
```

## Step 4 — reestablishment outcome

If the UE reestablished, follow `handover-end-to-end.md` (reestablishment is the
failure tail of a HO) and `ue-identity-map.md` to track whether the gNB reused
the UE context (direct RLF: CU `ue=` stable, new C-RNTI) or created a new one
(post-HO T304 expiry).

## Diagnosis template

```
Failure window: rnti 0x<RNTI>, slots <a>..<b>, ~<ts>
UL verdict: <DTX | gNB-decode-miss | channel-degradation | clean-stop>
  evidence: <correlate_radio rows; sinr trend; UE TX present/absent>
DL toward UE: <PDCCH/PDSCH present? ss_id anomaly?>
Conclusion: <which side failed and why, in NR terms>
```
