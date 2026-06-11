---
name: analyze-pcap
description: >
  Knowledge module for analyzing packet captures produced by an OCUDU
  application (`gnb`, `du`, `cu`, `cu_cp`, `cu_up`) — reference material on the
  Upper-PDU capture format, the NGAP/F1AP/E1AP/MAC-NR/RLC-NR protocols and
  procedures, `tshark` recipes, and helper scripts. Invoked by a higher-level
  inspect/run orchestrator skill when it needs to analyze pcap artifacts, or
  directly by a user to load pcap-analysis context (trigger phrases: "analyze this pcap",
  "look at the pcap", "what's in this capture", or a path ending in `.pcap` /
  `.pcapng`). It provides context and methodology; it does not drive an
  interactive analysis task — the calling agent does the work using this
  knowledge.
version: 0.1.0
user-invocable: true
allowed-tools: Bash(ls:*), Bash(grep:*), Bash(capinfos:*), Bash(tshark:*), Bash(python3:*), Bash(file:*), Bash(stat:*), Bash(wc:*), Bash(head:*), Bash(sort:*), Bash(uniq:*), Bash(awk:*), Bash(realpath:*), Bash(sha256sum:*), Bash(find:*), Edit, Write
---

# Analyze OCUDU pcap files

Analyze packet captures produced by OCUDU applications. The captures use the
Wireshark **Upper PDU** export format (link type 252) and contain
application-layer 3GPP PDUs (NGAP, F1AP, E1AP, MAC-NR, RLC-NR), one protocol
per file. A single test run typically produces five sibling pcaps in the same
directory: `mac.pcap`, `rlc.pcap`, `f1ap.pcap`, `e1ap.pcap`, `ngap.pcap` — all
sharing wall-clock epoch timestamps.

## What this skill provides

This is a **knowledge module**, not a task driver. It gives the calling agent
 the context needed to analyze OCUDU pcaps:

- `references/pcap-format.md` — the Upper-PDU capture format and dissector quirks.
- `references/protocols/` and `references/procedures/` — per-protocol field/filter
  references and per-procedure expected-sequence/failure-marker templates.
- `references/tshark-recipes.md` and `references/cross-pcap-correlation.md` —
  cross-cutting filter and correlation patterns.
- `references/scripts/` — pre-vetted helper scripts that emit compact summaries.
- `references/analysis-guide.md` — methodology for the three common activities
  (producing an overview, answering a targeted question, investigating a failure).

## How to use it

1. **Resolve the input** (§ Step 1) and **preflight** the file (§ Step 2).
2. Follow `references/analysis-guide.md` for the activity at hand, leaning on the
   helper scripts and the protocol/procedure references.
3. Apply the § Efficiency rules throughout.
4. If analysis surfaces a generalisable learning, persist it per § Memory &
   self-maintenance.

---

## Step 1 — Input resolution

```bash
realpath <user-path>
file <user-path>           # if a file
ls -lh <user-path>         # always
```

**Run directory** — a directory containing at least two of
`{mac.pcap, rlc.pcap, f1ap.pcap, e1ap.pcap, ngap.pcap}`. Treat all five as
one logical capture; cross-correlate by epoch timestamp.

**Single pcap** — a path to one `.pcap` / `.pcapng`. List sibling pcaps in the
same directory. For a deep investigation the caller may widen scope to include
the sibling pcaps for cross-protocol correlation; for a narrow question, stay
scoped to the file at hand.

**Neither** — the caller needs to supply a path.

---

## Step 2 — Preflight

Run once per session (cache in conversation memory; no need to repeat):

```bash
tshark -v 2>/dev/null | head -1     # confirm tshark is available (target: 4.4.7)
```

For every input file:

```bash
capinfos -aeucz <file.pcap>
```

Bail with a clear message if:
- File size is 0.
- `capinfos` reports a link layer other than `Wireshark Upper PDU` (DLT 252).
- The file does not exist.

On the first pcap of the session, confirm the Upper-PDU dispatcher binds to a
3GPP dissector by inspecting one frame:

```bash
tshark -r <file.pcap> -V -c 1 2>/dev/null | head -40
```

If the protocol name in the first frame's `wireshark-upper-pdu` field does not
match the expected dissector (`ngap`, `f1ap`, `e1ap`, `mac-nr`, `rlc-nr`), fall
back to `-d user_dlt 252,...` and document the case in
`references/pcap-format.md`.

---

## Step 3 — Follow the analysis guide

Load `references/analysis-guide.md` and follow the section that matches the
activity at hand — *Producing an overview*, *Answering a targeted question*, or
*Investigating a failure*. All three lean on the helper scripts in
`references/scripts/` and the protocol/procedure reference files in
`references/protocols/` and `references/procedures/`.

---

## Efficiency rules

- **Session cache dir.** All intermediate state (tshark caches, AppArmor-staged
  pcaps, large spills) lives under one per-session, user-private directory:
  `${CLAUDE_CODE_TMPDIR:-/tmp}/claude-skills-${CLAUDE_CODE_SESSION_ID}/`.
  It is shared with the `analyze-amari-ue-log` and `analyze-ocudu-gnb-log`
  skills so all three can cross-reference cached outputs in one run. Helper scripts resolve it automatically (see
  `references/scripts/utils.py::_CACHE_ROOT`); when spilling output yourself,
  write under that path with a descriptive prefix (`pcap-…`). The OS reaps
  `/tmp` on reboot — no manual cleanup needed.
- **Never** run `tshark -V` without `-c 1` or a single-frame filter
  (`-Y 'frame.number == N'`). Full verbose dumps blow up context.
- **Never** pipe an unbounded `tshark -T fields` result into context. Cap at
  200 rows with `head -n 200`; spill the rest into the cache dir as
  `pcap-cache-<sha>.tsv` and report the path.
- **Prefer** the helper scripts in `references/scripts/` over hand-crafted
  filter chains — they are pre-vetted, cache their tshark output, and emit
  compact summaries instead of raw frames.
- **Reuse** the cache: if `pcap-cache-<sha>.tsv` already exists in the cache
  dir for a given pcap and column set, do not re-invoke tshark — post-filter
  the cached file instead.
- **AppArmor**: on Ubuntu the Canonical AppArmor profile on tshark restricts
  reads to `/tmp`. The helper scripts auto-stage pcaps into the cache dir's
  `pcap-stage/` subfolder — see `references/pcap-format.md` § AppArmor.
- For run directories with multiple UEs, scope tshark queries by UE identifier
  early — the cross-product of 5 pcaps × many UEs is large.

---

## Memory & self-maintenance

This skill improves itself over time. When analysis surfaces a generalisable
learning — or reveals that the skill's own docs or scripts are wrong — propose the
change and, **only after the user approves**, apply it with `Edit` (or `Write` for
a brand-new reference file).

**Only ever edit files inside this skill's own `references/` tree.** Never touch
files elsewhere in the repo, and never run git/commit — edits are left as diffs
for the user to review and commit.

Three kinds of edit:

1. **Add a learning** — put it where a reader would naturally look, matching the
   surrounding format (extend a table row, add a line to a code block, add a bullet
   to an existing list). **Do not prepend dates/timestamps.** Natural homes:
   - new tshark filter → `references/protocols/<proto>.md` § Key tshark filters
     (or `references/tshark-recipes.md` if cross-cutting)
   - corrected field name / procedure code → the canonical row in that protocol's
     § Key tshark filters / § Common procedures and codes
   - Upper-PDU framing or dissector-binding quirk → `references/pcap-format.md`
     (the relevant section, e.g. § AppArmor on Ubuntu/Debian)
   - failure signature → `references/procedures/<proc>.md` § Failure markers
   - cross-protocol correlation pattern → `references/cross-pcap-correlation.md`
   If a learning is substantial and distinct, create a **new file** following the
   template of its siblings and wire it in:
   - new `procedures/<name>.md` → add a row to the dispatch table in
     `references/analysis-guide.md` § Investigating a failure
   - new `scripts/<name>.py` → document its invocation in
     `references/analysis-guide.md`, the relevant procedure file, and
     `protocols/<proto>.md` § Parsing script
2. **Fix existing content** — correct a stale tshark filter, wrong field name, or
   outdated statement; dedupe/reorganise a reference file.
3. **Fix a helper script** — when analysis exposes a bug in
   `references/scripts/*.py`, correct it.

For every edit:
- **Propose first** — show the file path, the section, and the exact text/diff.
- **Confirm** via `AskUserQuestion`: **Apply** / **Edit wording** *(open text)* / **Skip**.
- **Apply** only on approval.
- **After editing a `.py` script**, run `python3 -m py_compile <script>` to confirm
  it still compiles (and, when practical, re-run it on the current input to confirm
  behaviour). If it breaks, fix or revert before finishing.
- **Report** what changed.

**Never** save specific RNTIs, UE-IDs, frame numbers, run timestamps, KPIs, or
per-run root-cause narratives — those don't generalise. Operator-/preference-level
knowledge (user shortcuts, local quirks, named conventions) goes to the project's
auto-memory directory under `~/.claude/projects/<project-key>/memory/`, not to
`references/`.

**Maintenance trigger**: if the user says "reorganize pcap knowledge", re-read all
files under `references/`, dedupe, fix stale tshark syntax, and report a
one-paragraph summary of what changed — proposing each edit under the same confirm
flow above.

