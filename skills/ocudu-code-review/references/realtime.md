# OCUDU Code Review — Real-time paths

Applies only to code reachable from a real-time path; see "Determining
reachability" below.

- **New heap allocation**, including container growth without reserved
  capacity and `std::function` captures beyond small-buffer size.
- **New blocking call**: lock or condition-variable wait, `sleep`, blocking
  I/O, or a call into a component that blocks. If the diff genuinely needs
  one, surface it for the user to confirm the primitive is appropriate.
- **New unbounded-latency operation**: a loop bounded by external input,
  logging that allocates or locks, RTTI, or new virtual dispatch in a very hot
  inner loop.

## Determining reachability

Never infer "real-time path" from a directory name.

Trace callers of the touched functions up to either a hot entry point (a
per-slot, per-symbol, per-TTI or per-PDU handler such as `run`,
`process_slot`, `handle_symbol`, a scheduler tick or a PHY/MAC callback) or a
non-real-time context (start-up, config parsing, an RRC/NGAP/F1AP handler, a
background worker). If still unsure, say so in the finding rather than
dropping it.
