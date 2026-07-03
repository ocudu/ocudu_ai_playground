# NGAP — pcap observation (gNB ↔ AMF, N2 interface)

How NGAP shows up in `ngap.pcap` and how to query it. The **semantics** —
procedure-code meanings, identifier model, failure signatures — are
artifact-agnostic and live in `../../common/protocols/ngap.md`; this file is the
tshark/observation layer only.

The `ngap.pcap` captures every NGAP PDU on the N2 link. Useful for failures
between UE registration and PDU-session establishment, and for AMF rejection
causes.

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

# Specific procedures (codes/meanings: ../../common/protocols/ngap.md)
tshark -r ngap.pcap -Y 'ngap.procedureCode == 15'   # InitialUEMessage
tshark -r ngap.pcap -Y 'ngap.procedureCode == 14'   # InitialContextSetup
tshark -r ngap.pcap -Y 'ngap.procedureCode == 29'   # PDUSessionResourceSetup
tshark -r ngap.pcap -Y 'ngap.procedureCode == 41'   # UEContextRelease
tshark -r ngap.pcap -Y 'ngap.procedureCode ==  0'   # AMFConfigurationUpdate
```

## Identifier fields (tshark)

- `ngap.RAN_UE_NGAP_ID` — gNB-assigned, present from InitialUEMessage onward.
- `ngap.AMF_UE_NGAP_ID` — AMF-assigned, present from InitialContextSetupRequest
  onward.
- See `../cross-pcap-correlation.md` for joining to F1AP / E1AP, and
  `../../common/identifiers.md` for the identifier model.

## Parsing script

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/ngap_procedures.py <ngap.pcap>
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/ngap_procedures.py <ngap.pcap> --ue <N>
python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/ngap_procedures.py <ngap.pcap> --failures-only

python3 ${CLAUDE_SKILL_DIR}/scripts/pcap/extract_proc_codes.py <ngap.pcap> --proto ngap
```
