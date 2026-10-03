# OCUDU Code Review — Checklists

## Contents

- [Correctness](#correctness): OCUDU-specific bug patterns.
- [OCUDU C++ conventions](#ocudu-c-conventions): member ordering and error
  handling.
- [Comment style](#comment-style): rules for comments the diff adds or changes.

## Correctness

- Wraparound of sequence numbers and slot/frame counters.
- A new field touched from more than one thread or callback context without
  its neighbours' synchronization.

## OCUDU C++ conventions

- **Member ordering**: private members after public ones, except constants
  (`static constexpr`, `enum`) and type aliases the public interface depends
  on, which come first.
- **Error handling**: return values (status/`expected`-style) over exceptions.
  Flag a new `throw`, or a fallible function returning `void` or swallowing the
  error.

## Comment style

Applies to comments the diff adds or changes, not untouched ones.

- No end-of-line comments.
- In function bodies: *why*, not *what*.
- On public interfaces: a comment naming the specific callers/flows that use
  the interface is a smell.
- No historical/process language: "added", "removed", "changed", "now
  handles", "this used to".
- No commented-out code.
- No `--` dashes; sentences end with `.`.
