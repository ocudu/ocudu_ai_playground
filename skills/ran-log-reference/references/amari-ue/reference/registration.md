# Registration procedure

UE-log observation surface. For diagnosing a *failed* registration, see
`../troubleshooting/registration.md`.

## Expected sequence (single UE, initial attach)

```
[PROD]  SIM-Event: power_on
[NAS]   UE New state : 5GMM-NULL CM-IDLE
[PHY]   DL - 00 - PSS: n_id_cell=N         ← cell search
[RRC]   DL <sfn> 00 BCCH-BCH-NR: MIB       ← MIB decoded
[RRC]   DL <sfn> 00 BCCH-NR: SIB1          ← SIB1 decoded
   ↓ (stdout: "Cell 0: SIB found")
[PHY]   UL - 00 - PRACH: ...               ← random access
[RRC]   DL - 00 - CCCH-NR: RRC setup       ← network accepts
[NAS]   0001 New state : 5GMM-REGISTERED-INITIATED CM-IDLE   ← started
[RRC]   UL 0001 00 CCCH-NR: RRC setup request
[RRC]   DL 0001 00 CCCH-NR: RRC setup
[RRC]   UL 0001 00 DCCH-NR: RRC setup complete
[NAS]   0001 New state : 5GMM-REGISTERED-INITIATED CM-CONNECTED
[RRC]   DL 0001 00 DCCH-NR: Security mode command
[RRC]   UL 0001 00 DCCH-NR: Security mode complete
[RRC]   DL 0001 00 DCCH-NR: RRC reconfiguration   ← bearer setup
[RRC]   UL 0001 00 DCCH-NR: RRC reconfiguration complete
[NAS]   0001 New state : 5GMM-REGISTERED CM-CONNECTED        ← attached!
```

## Expected sequence (deregistration / power off)

```
[PROD]  SIM-Event: power_off
[NAS]   0001 New state : 5GMM-DEREGISTERED-INITIATED CM-CONNECTED
# (optional) network-initiated RRC release on DCCH-NR DL may follow — NOT seen in
# the OCUDU baseline fixtures, where deregistration is NAS-only.
[NAS]   0001 New state : 5GMM-DEREGISTERED CM-CONNECTED
[NAS]   0001 New state : 5GMM-NULL CM-CONNECTED
[NAS]   0001 New state : 5GMM-NULL CM-IDLE
[PROD]  SIM-Event: quit
# Ended on ...
```

## Diagnosing failures

For the investigation checklist (and failure markers), see
`../troubleshooting/registration.md`.
