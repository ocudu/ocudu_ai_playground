# OCUDU Code Review — Checklists

OCUDU doesn't yet have a single canonical style/contribution doc. Until it
does, these checklists are the working defaults — update them in place once
a canonical doc exists, rather than duplicating it here.

## general

**Correctness**
- Logic errors: off-by-one, inverted conditions, wrong operator, incorrect
  loop bounds.
- Edge cases the diff's own tests (if any) don't cover: empty containers,
  zero/negative counts, first/last element, wraparound of sequence numbers or
  slot/frame counters.
- Resource lifetime: use-after-move, dangling references/iterators after a
  container reallocates, double-free, missing null/empty checks before
  dereference.
- Concurrency: data races on shared state touched from more than one thread
  or callback context; check whether a new field needs the same
  synchronization as its neighbors.

**OCUDU C++ conventions**
- **Member ordering**: private members after public members, except
  constants (`static constexpr`, `enum`) and type aliases the public
  interface depends on, which come first. Flag a new private member inserted
  before the public section, or a new public member appended after private
  members.
- **Error handling**: prefer return values (status/`expected`-style) over
  exceptions for error propagation. Flag a new `throw`, or a new function
  that can fail but returns `void`/silently swallows the error.
- **No exceptions across real-time paths**: independent of the general
  return-over-exceptions preference, any `throw` reachable from a real-time
  path is a `realtime`-mode finding, not just a style one — see below.

**Comment style** (applies to comments the diff adds or changes, not
pre-existing comments left untouched)
- No end-of-line comments — a comment sits on its own line above the code it
  describes.
- Inside function bodies: comments explain *why*, not *what*; if the comment
  just restates the next line in words, flag it as removable rather than
  incorrect.
- On public interfaces (declarations in headers): the *why* isn't required,
  but a comment naming the specific callers/flows that use the interface is
  a smell — interface docs shouldn't be coupled to one caller.
- No historical/process language: "added", "removed", "changed", "now
  handles", "this used to" — these are only meaningful diffed against a
  version the reader doesn't have.
- No commented-out code.
- No `--` dashes; sentences end with `.`.

## realtime

The question for every item below is *reachability*, not file location — see
"Determining reachability" first.

- **New heap allocation** on a reachable path: `new`, container
  growth/insertion without a pre-sized/reserved capacity, `std::string`
  construction/concatenation, `std::function` capturing by value where the
  capture exceeds small-buffer-optimization size, any STL container default
  construction that isn't provably empty-and-unused.
- **New blocking call**: mutex/semaphore/condition-variable wait, `sleep`,
  blocking I/O (file, socket, syscall), or any call into a component known to
  block (check its declaration/docs, don't assume from the name). If a diff
  *does* need a blocking primitive on what looks like a hot path, don't just
  flag it — surface it explicitly for the user to confirm the primitive is
  appropriate, per project convention.
- **New unbounded-latency operation**: a loop whose bound comes from
  untrusted/external input rather than a compile-time or config-time
  constant, logging/formatting calls that allocate or lock internally,
  `dynamic_cast`/RTTI, virtual dispatch through a newly-introduced
  indirection where the path was previously statically resolved (lower
  severity — flag only if it's on a very hot inner loop).
- **New exception path**: a `throw`, or a call to something that can throw,
  newly reachable from a real-time path.

### Determining reachability

Don't infer "real-time path" from a file's directory name alone — OCUDU's
directory layout isn't part of this checklist's contract, and guessing from
paths produces false positives/negatives as the tree evolves. Instead:

1. Find the function(s) the diff touches.
2. Trace their callers (`grep`/`Grep` for the function name, follow it up the
   call chain) until you reach a recognizable hot entry point — a per-slot,
   per-symbol, per-TTI, or per-PDU handler (names like `run`, `process_slot`,
   `handle_symbol`, a scheduler tick, a PHY/MAC callback invoked once per
   radio time unit) or, conversely, a clearly non-real-time context
   (start-up/config parsing, a control-plane RRC/NGAP/F1AP handler that runs
   at message rate rather than symbol rate, a background/worker thread doing
   non-latency-sensitive work).
3. If you can't determine reachability confidently either way after a
   reasonable trace, say so in the finding rather than silently skipping it —
   e.g. "new allocation in `foo()`; couldn't confirm whether callers include
   a real-time path — verify before merging."

## security

Treat as untrusted any data that originates over the air or from another
network element before it's validated: RRC/NGAP/F1AP/E1AP messages, MAC/RLC/
PDCP PDUs, ASN.1-decoded fields, anything read from a UE- or peer-supplied
buffer. Also treat as untrusted anything read from an external config/YAML
file if the value flows into a size/index/allocation.

- **Bounds/length handling**: a length or count field from an untrusted
  source used to index, size an allocation, or bound a loop without a
  validity check against the buffer's actual size.
- **Integer overflow/underflow**: arithmetic on untrusted lengths/counts
  (especially subtraction or multiplication) that could wrap and then feed a
  bounds check or allocation size.
- **Signedness bugs**: a signed/unsigned mismatch that changes the outcome of
  a bounds comparison.
- **Unchecked casts**: `reinterpret_cast`, C-style casts, or a `static_cast`
  narrowing an untrusted value, without a preceding range/validity check.
- **ASN.1/PDU decode paths**: a new decode branch that trusts a
  length/tag/count from the wire before validating it against the remaining
  buffer.
- **Raw memory ops**: `memcpy`/`memmove`/`memset` (or manual loop
  equivalents) where the size argument derives from untrusted input.
- **Config/deserialization**: a new YAML/JSON field that flows into a size,
  index, or path without validation.

Findings here should name the specific untrusted source (message type/field)
and the specific sink (index, size, allocation) — a generic "missing
validation" note without a concrete failure scenario isn't actionable enough
to report.
