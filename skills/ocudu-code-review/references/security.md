# OCUDU Code Review — Security

Untrusted = anything from the air or from another network element before it's
validated: RRC/NGAP/F1AP/E1AP messages, MAC/RLC/PDCP PDUs, ASN.1-decoded
fields, UE- or peer-supplied buffers. Also external config/YAML values that
flow into a size, index or allocation.

Flag an untrusted value reaching an index, size, loop bound, cast, raw memory
op or allocation without validation, including overflow or signedness bugs
that defeat the check. In ASN.1/PDU decode paths, check that a length, tag or
count from the wire is validated against the remaining buffer.

Name the specific untrusted source (message type/field) and the specific sink
(index, size, allocation).
