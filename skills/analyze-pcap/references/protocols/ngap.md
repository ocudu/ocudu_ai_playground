# NGAP — gNB ↔ AMF (N2 interface)

## Purpose

NGAP carries the control-plane exchanges between the gNB and the AMF in the 5G
core. The `ngap.pcap` in an OCUDU run captures every NGAP PDU sent or received
on the N2 link. Useful for diagnosing failures that happen between UE
registration and PDU-session establishment, and for AMF rejection causes.

## Key tshark filters

```bash
# All NGAP messages with procedure code, UE IDs
tshark -r ngap.pcap \
    -T fields -E separator=$'\t' \
    -e frame.number -e frame.time_epoch \
    -e ngap.procedureCode -e ngap.RAN_UE_NGAP_ID -e ngap.AMF_UE_NGAP_ID

# Only failures / rejects
tshark -r ngap.pcap -Y 'ngap.unsuccessfulOutcome_element || ngap.cause'

# Single-UE lifecycle
tshark -r ngap.pcap -Y 'ngap.RAN_UE_NGAP_ID == <N>'

# Specific procedures
tshark -r ngap.pcap -Y 'ngap.procedureCode == 15'   # InitialUEMessage
tshark -r ngap.pcap -Y 'ngap.procedureCode == 14'   # InitialContextSetup
tshark -r ngap.pcap -Y 'ngap.procedureCode == 29'   # PDUSessionResourceSetup
tshark -r ngap.pcap -Y 'ngap.procedureCode == 41'   # UEContextRelease
tshark -r ngap.pcap -Y 'ngap.procedureCode ==  0'   # AMFConfigurationUpdate
```

## Identifier mapping

- `ngap.RAN_UE_NGAP_ID` — gNB-assigned, present from InitialUEMessage onwards.
- `ngap.AMF_UE_NGAP_ID` — AMF-assigned, present from InitialContextSetupRequest
  onwards.
- See `../cross-pcap-correlation.md` for joining to F1AP / E1AP.

## Common procedures and codes

| Code | Procedure | Initiator | Notes |
|---:|---|---|---|
|  0 | AMFConfigurationUpdate | AMF | infrastructure |
|  1 | RANConfigurationUpdate | gNB | infrastructure |
| 14 | InitialContextSetup | AMF | UE registration completion |
| 15 | InitialUEMessage | gNB | First NGAP for a UE |
| 16 | NASNonDeliveryIndication | gNB | NAS not delivered |
| 21 | NGSetup | gNB | NG-C setup at startup |
| 27 | Paging | AMF | DL idle-mode paging |
| 29 | PDUSessionResourceSetup | AMF | establish PDU session |
| 36 | UEContextModification | AMF | |
| 41 | UEContextRelease | AMF or gNB | end of UE in NG |
| 46 | UplinkNASTransport | gNB | NAS to AMF |
| 47 | DownlinkNASTransport | AMF | NAS to UE |

## Common failure signatures

- **NGSetupFailure**: gNB rejected by AMF at startup — check PLMN/TAC config.
- **InitialContextSetupFailure**: AMF rejected the UE — cause IE distinguishes
  authentication failure, subscription issue, config mismatch.
- **PDUSessionResourceSetupResponse with `failedListPDUSessions`**: UPF or
  E1AP problem; pair with `e1ap.pcap` BearerContextSetup outcome.
- **UEContextReleaseCommand with cause `radio-connection-with-ue-lost`**:
  AMF-initiated release after RLF reported by gNB.
- **UEContextReleaseCommand with cause `user-inactivity`**: normal idle
  release — not a failure.
- **InitialUEMessage without subsequent InitialContextSetupRequest**: AMF
  silently dropped the registration — check connectivity / AMF logs.

## Parsing script

```bash
python3 ${CLAUDE_SKILL_DIR}/references/scripts/ngap_procedures.py <ngap.pcap>
python3 ${CLAUDE_SKILL_DIR}/references/scripts/ngap_procedures.py <ngap.pcap> --ue <N>
python3 ${CLAUDE_SKILL_DIR}/references/scripts/ngap_procedures.py <ngap.pcap> --failures-only

python3 ${CLAUDE_SKILL_DIR}/references/scripts/extract_proc_codes.py <ngap.pcap> --proto ngap
```

## Accumulated knowledge

*Append: new procedure-code observations, cause-IE values you've encountered,
field-name variations across tshark versions.*
