# Troubleshooting: UE attach (VIAVI)

Failure playbook for a UE that never fully attaches. For the expected
attach sequence, see `../reference/ue-attach.md`.

## Failure markers

| Marker | Meaning |
|---|---|
| `L2 Random Access Error :UE Id:N (Result: …)` | PRACH never completed → see `random-access.md` |
| `MTE 0 NR CONNECTION FAILED IND:UE Id:N` | RRC connection attempt failed (no `CONNECTION IND` follows) |
| `CONNECTION IND` but no `REGISTRATION IND` | RRC up but 5GMM registration never completed — a core/NAS-side problem |
| `REGISTRATION IND` absent for a UE that has RA Complete | registration stalled; check the OCUDU gNB log / NGAP pcap |
| `NR PLMN LOSS IND` | UE lost the PLMN mid-session |

## Investigation checklist

1. Did RA complete? `--ue N --event "Random Access"` — if only `Initiated`/`Error`,
   the problem is at random access (next file).
2. Did the connection come up? `--ue N --event "NR CONNECTION"` — `CONNECTION
   FAILED IND` vs `CONNECTION IND`.
3. Did registration complete? `--ue N --event "NR REGISTRATION IND"`.
4. If RA + connection succeeded but registration didn't, the VIAVI side did its
   job — cross-check the **OCUDU gNB log** (RRC setup, NGAP Initial UE Message)
   and the **NGAP pcap** for the network-side cause.

## Cross-references

- ../reference/ue-attach.md
