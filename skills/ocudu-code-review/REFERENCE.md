# OCUDU Code Review — Checklists

Working defaults until OCUDU has a canonical style/contribution doc; update
them in place once it does.

## Correctness

- Logic errors: off-by-one, inverted conditions, wrong operator, wrong loop
  bounds.
- Edge cases the diff's own tests miss: empty containers, zero/negative
  counts, first/last element, wraparound of sequence numbers or slot/frame
  counters.
- Resource lifetime: use-after-move, dangling references/iterators after a
  container reallocates, double-free, missing null/empty check before a
  dereference.
- Concurrency: data races on state touched from more than one thread or
  callback context; whether a new field needs its neighbours' synchronization.

## OCUDU C++ conventions

- **Member ordering**: private members after public ones, except constants
  (`static constexpr`, `enum`) and type aliases the public interface depends
  on, which come first. Flag a new private member before the public section,
  or a new public member after the private ones.
- **Error handling**: return values (status/`expected`-style) over exceptions.
  Flag a new `throw`, or a new fallible function returning `void` or
  swallowing the error.
- **No exceptions across real-time paths**: a `throw` reachable from a
  real-time path is a real-time finding, not a style one.

## Comment style

Applies to comments the diff adds or changes, not untouched ones.

- No end-of-line comments — a comment sits above the code it describes.
- In function bodies: *why*, not *what*. A comment restating the next line is
  removable, not incorrect.
- On public interfaces: a comment naming the specific callers/flows that use
  the interface is a smell.
- No historical/process language: "added", "removed", "changed", "now
  handles", "this used to".
- No commented-out code.
- No `--` dashes; sentences end with `.`.

## Real-time paths

Every item here is a question of *reachability*, not file location — settle
that first, per "Determining reachability" below.

- **New heap allocation**: `new`, container growth/insertion without reserved
  capacity, `std::string` construction/concatenation, `std::function` whose
  capture exceeds small-buffer-optimization size, any STL container
  construction not provably empty-and-unused.
- **New blocking call**: mutex/semaphore/condition-variable wait, `sleep`,
  blocking I/O (file, socket, syscall), or a call into a component known to
  block (check its declaration/docs, don't assume from the name). If the diff
  genuinely needs one on a hot path, surface it for the user to confirm the
  primitive is appropriate.
- **New unbounded-latency operation**: a loop bounded by untrusted/external
  input rather than a compile- or config-time constant, logging/formatting
  that allocates or locks internally, `dynamic_cast`/RTTI, virtual dispatch
  through a new indirection where the path was statically resolved (flag only
  on a very hot inner loop).
- **New exception path**: a `throw`, or a call that can throw, newly reachable
  from a real-time path.

### Determining reachability

Never infer "real-time path" from a directory name.

1. Find the function(s) the diff touches.
2. `Grep` their callers up the chain until you reach either a hot entry point
   — a per-slot, per-symbol, per-TTI or per-PDU handler (`run`,
   `process_slot`, `handle_symbol`, a scheduler tick, a PHY/MAC callback fired
   once per radio time unit) — or a clearly non-real-time context (start-up/
   config parsing, a control-plane RRC/NGAP/F1AP handler running at message
   rate, a background worker doing non-latency-sensitive work).
3. Still unsure after a reasonable trace: say so in the finding rather than
   dropping it.

## Security

Untrusted = anything from the air or from another network element before it's
validated: RRC/NGAP/F1AP/E1AP messages, MAC/RLC/PDCP PDUs, ASN.1-decoded
fields, UE- or peer-supplied buffers. Also external config/YAML values that
flow into a size, index or allocation.

- **Bounds/length handling**: an untrusted length/count used to index, size an
  allocation or bound a loop without a check against the buffer's real size.
- **Integer overflow/underflow**: arithmetic on untrusted lengths/counts
  (especially subtraction, multiplication) that could wrap before feeding a
  bounds check or allocation size.
- **Signedness bugs**: a signed/unsigned mismatch that changes a bounds
  comparison's outcome.
- **Unchecked casts**: `reinterpret_cast`, C-style cast, or a `static_cast`
  narrowing an untrusted value, with no preceding range check.
- **ASN.1/PDU decode paths**: a new decode branch trusting a length/tag/count
  from the wire before validating it against the remaining buffer.
- **Raw memory ops**: `memcpy`/`memmove`/`memset` (or manual equivalents)
  whose size derives from untrusted input.
- **Config/deserialization**: a new YAML/JSON field flowing into a size, index
  or path without validation.

Name the specific untrusted source (message type/field) and the specific sink
(index, size, allocation).
