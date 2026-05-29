---
name: analyze-pcap
description: >
  Use this skill when the user asks to analyze, summarize, query, or investigate
  a packet capture produced by an OCUDU application (`gnb`, `du`, `cu`, `cu_cp`,
  `cu_up`). Trigger phrases include: "analyze this pcap", "look at the pcap",
  "give me an overview of this pcap", "what's in this capture", "why did X
  happen in this pcap", "investigate this run", "root-cause this failure",
  "what went wrong with", "debug this test", "why did this test fail", or
  a path ending in `.pcap` / `.pcapng`, or a path under `.../ocudu-gnb-*/`,
  or a retina test log path (e.g. `retina/log/tests/*/test_gnb[...]`).
  The skill operates in three explicit modes — `overview`, `query`,
  `investigation` — and uses `tshark` plus helper scripts to keep analysis
  cheap. When in doubt about scope or intent, the skill asks the user via
  AskUserQuestion rather than assuming.
version: 0.1.0
user-invocable: true
context: fork
allowed-tools: Bash(ls:*), Bash(grep:*), Bash(capinfos:*), Bash(tshark:*), Bash(python3:*), Bash(file:*), Bash(stat:*), Bash(wc:*), Bash(head:*), Bash(realpath:*), Bash(sha256sum:*), Bash(find:*), Edit, Write
---

# Analyze OCUDU pcap files

Analyze packet captures produced by OCUDU applications. The captures use the
Wireshark **Upper PDU** export format (link type 252) and contain
application-layer 3GPP PDUs (NGAP, F1AP, E1AP, MAC-NR, RLC-NR), one protocol
per file. A single test run typically produces five sibling pcaps in the same
directory: `mac.pcap`, `rlc.pcap`, `f1ap.pcap`, `e1ap.pcap`, `ngap.pcap` — all
sharing wall-clock epoch timestamps.

## Overall flow

1. **Input resolution** — determine whether the user gave a single pcap or a
   run directory, and confirm the file format.
2. **Mode dispatch** — pick one of `overview`, `query`, `investigation` from
   the user's wording; ask if ambiguous.
3. **Mode branch** — load and follow `references/mode-{overview,query,investigation}.md`.
4. **Persist learnings** — weave any generalisable findings into the natural place
   in `references/` (see § Memory & self-maintenance).

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
same directory. If the user picked `investigation` mode and siblings exist,
ask via `AskUserQuestion`:
- **Stay scoped** — analyse only the file the user pointed at.
- **Widen to run** — include the sibling pcaps for cross-protocol correlation.

**Neither** — ask the user to provide a path.

---

## Step 2 — Mode dispatch

Match the user's wording against this table. If multiple modes plausibly match,
ask via `AskUserQuestion` with the three modes as options.

| User wording | Mode |
|---|---|
| "overview", "summary", "what's in this pcap", "describe this capture", no specific question | `overview` |
| explicit question form ("why", "when", "how many", "which", "did X happen") | `query` |
| "investigate", "root cause", "debug", "why did this fail", "find the bug" | `investigation` |

When the user passed multiple  instructions (e.g. "give me an overview and then
investigate why the handover failed"), do them in order — overview first,
then ask before entering investigation.

---

## Step 3 — Preflight

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

## Step 4 — Mode branch

Load the matching file and follow it:

- `references/mode-overview.md`
- `references/mode-query.md`
- `references/mode-investigation.md`

All three modes share the helper scripts in `references/scripts/` and the
protocol/procedure reference files in `references/protocols/` and
`references/procedures/`.

---

## Efficiency rules

- **Session cache dir.** All intermediate state (tshark caches, AppArmor-staged
  pcaps, large spills) lives under one per-session, user-private directory:
  `${CLAUDE_CODE_TMPDIR:-/tmp}/claude-skills-${CLAUDE_CODE_SESSION_ID}/`.
  It is shared with the `analyze-amari-ue-log` skill so both can cross-reference
  cached outputs in one run. Helper scripts resolve it automatically (see
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
   - new `procedures/<name>.md` → add a row to the dispatch list in
     `references/mode-investigation.md` § Phase B
   - new `scripts/<name>.py` → document its invocation in the relevant `mode-*.md`,
     procedure file, and `protocols/<proto>.md` § Parsing script
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

