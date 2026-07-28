# correlate — conventions

Entry point for the **cross-artifact** type: lining up the same event across the
Amarisoft UE log, the OCUDU gNB log, the pcaps, and (where present) the VIAVI
tester log for a whole run.

**Read `cross-correlation.md` first** — it is the master clock/slot/identifier
model and every correlation below depends on it.

## Subtree layout

- **`cross-correlation.md`** — the master model: timestamp format per source, how
  to establish the per-run clock offset, the exact radio key, matching-key
  priority, and the signals only this layer can see. **Start here.**
- **`components.md`** — how a Retina `test_gnb[...]` directory is laid out, which
  type analyses each artifact, and how `testbed.json` maps components to the
  network.
- **`ue-identity-map.md`** — the UE identifier model across sources: which ID each
  source uses and how they chain.
- **`procedures/`** — cross-artifact traces: the same procedure seen from every
  source, with the join key named at each hop (`attach-end-to-end.md`,
  `handover-end-to-end.md`, `radio-link-failure.md`).
- **`overview.md`** / **`query.md`** / **`investigate.md`** — this type's slots for
  the three activities; the `references/mode-*.md` playbooks drive and pull from
  them.

## Resolve & scope

The dispatcher runs `scripts/correlate/resolve.py`, which classifies a whole run
directory spanning **≥2 RAN application components** and prints the components,
their artifacts, the `testbed.json` map, and the clock anchors, ending in a
`verdict:` line. **Bail if the verdict is not OK.**

**Scope** — this type composes the per-artifact subtrees it joins (`ocudu`,
`amari-ue`, `pcap`, `viavi`); load those *in addition* when a correlation needs
one side's parsing detail. This is the one type permitted to reach into siblings.

## Efficiency deltas

- **Never assume a shared wall-clock.** Same-process sources (a `gnb.log` and the
  pcaps that process wrote) are Δ≈0 by construction; off-host sources (VIAVI
  tester, a remote 5GC, a UE sim on another box) are not. `align_clocks.py`
  *verifies* the same-clock sources and the UE↔gNB PHY slot alignment — it does
  **not** measure an off-host offset, and there is no tool that does. For an
  off-host source, either avoid wall-clock entirely (preferred) or derive Δ by
  hand from one event pair joined on a clock-independent key — for VIAVI, the
  `Random Access Complete` TC-RNTI ↔ the gNB's `c-rnti=` (see
  `ue-identity-map.md` § Joining via the VIAVI log).
- **Prefer the clock-independent key.** For radio events, `(SFN.slot, RNTI)` is
  exact and immune to clock skew — use it over wall-clock whenever both sides
  report slots.
- **Scope by `--rnti` early.** The cross-product of 64 UEs × many slots is large;
  narrow to one UE before joining.
- Write cached outputs with the `correlate-` prefix so they don't collide with the
  per-type caches (see `SKILL.md` § Efficiency rules).
