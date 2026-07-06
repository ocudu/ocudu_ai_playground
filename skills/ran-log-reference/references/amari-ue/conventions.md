# amari-ue conventions

Type-specific deltas for `amari-ue` artifacts (Amarisoft UE simulator). The
shared resolve / efficiency / memory flow lives in the skill `SKILL.md`; this
file carries only what is particular to Amarisoft UE logs.

A single run directory typically contains:

| File | Description |
|---|---|
| `ue.log` | Detailed per-layer protocol trace (NAS/RRC/PHY/MAC/RLC/PDCP) |
| `stdout.log` | Console output: UE stats table, CBR traffic results, warnings |
| `amarisoft_ue.cfg` | JSON5 configuration: cell groups, UE list, sim events |
| `ps_info_lteue-avx2.txt` | Process CPU/memory snapshot (rarely needed) |

Ignore `metrics.json` — it is empty in these runs.

## Subtree layout

Debugging is symptom-first, so the docs split by role:

- **`troubleshooting/`** — per-procedure failure playbooks (failure markers /
  investigation checklist) for registration, data-session, handover. Start here
  from a symptom; each cites the expected-sequence `reference/` doc.
- **`reference/`** — lazily-loaded knowledge: format refs (`log-format.md`,
  `config-format.md`) and the expected-sequence procedure refs (sequence +
  vocabulary **only**; failure content lives in the paired `troubleshooting/`
  doc).
- top level — the entry point (`conventions.md`) and the methodology + failure
  dispatch (`analysis-guide.md`).

The `analysis-guide.md` § Investigating a failure dispatch table maps each symptom
to the `troubleshooting/` doc to load.

## Resolve & scope

The dispatcher runs `scripts/amari-ue/resolve.py`, which accepts a `ue.log`
file, a run directory, an `amarisoft-ue-N/` component dir, or a Retina
`test_gnb[...]` dir, and resolves to the latest run directory holding a `ue.log`.
It prints the resolved run dir, the analysis artifacts present (`ue.log`,
`stdout.log`, `amarisoft_ue.cfg`), and a `verdict:` line; it exits non-zero
(`BAIL`) if no `ue.log` is found or it is empty. **Bail if the verdict is not
OK.** (UE logs are plain text — there is nothing to validate beyond presence, so
this is resolution + inventory, not a preflight.)

**Scope** — when a `test_gnb[...]` dir holds more than one UE component (e.g.
`amarisoft-ue-1` + `amarisoft-ue-2`), `resolve.py` reports them and notes which
one it resolved to; scope explicitly to the UE you mean before going further.

## Efficiency rules (amari-ue)

- **Never** read raw `ue.log` into context — it can be more than 100k lines.
  Always grep for specific patterns or use a helper script.
- Spill larger results to `<cache-dir>/amari-<purpose>-<sha>.txt` (use the
  `amari-` prefix) and report the path.
- `stdout.log` is short (30–100 lines) — safe to read in full.
- `amarisoft_ue.cfg` is short (100–150 lines) — safe to read in full.
- In multi-UE mode (`ue_count > 1`), scope grep queries by UE ID early.
