---
name: analyze-pcap
description: >
  Use this skill when the user asks to analyze, summarize, query, or investigate
  a packet capture produced by an OCUDU application (`gnb`, `du`, `cu`, `cu_cp`,
  `cu_up`). Trigger phrases include: "analyze this pcap", "look at the pcap",
  "give me an overview of this pcap", "what's in this capture", "why did X
  happen in this pcap", "investigate this run", "root-cause this failure", or
  a path ending in `.pcap` / `.pcapng`, or a path under `.../ocudu-gnb-*/`.
  The skill operates in three explicit modes — `overview`, `query`,
  `investigation` — and uses `tshark` plus helper scripts to keep analysis
  cheap. When in doubt about scope or intent, the skill asks the user via
  AskUserQuestion rather than assuming.
version: 0.1.0
user-invocable: true
context: fork
agent: Explore
allowed-tools: Bash(ls:*), Bash(grep:*), Bash(capinfos:*), Bash(tshark:*), Bash(python3:*), Bash(jq:*), Bash(file:*), Bash(stat:*), Bash(wc:*), Bash(head:*), Bash(realpath:*), Bash(sha256sum:*), Bash(find:*)
---

# Analyze OCUDU pcap files

Analyze packet captures produced by OCUDU applications. The captures use the
Wireshark **Upper PDU** export format (link type 252) and contain
application-layer 3GPP PDUs (NGAP, F1AP, E1AP, MAC-NR, RLC-NR), one protocol
per file. A single test run typically produces five sibling pcaps in the same
directory: `mac.pcap`, `rlc.pcap`, `f1ap.pcap`, `e1ap.pcap`, `ngap.pcap` — all
sharing wall-clock epoch timestamps.

For OCUDU **log** analysis use the sibling skill `analyze-ocudu-log` instead.

## Overall flow

1. **Input resolution** — determine whether the user gave a single pcap or a
   run directory, and confirm the file format.
2. **Mode dispatch** — pick one of `overview`, `query`, `investigation` from
   the user's wording; ask if ambiguous.
3. **Mode branch** — load and follow `references/mode-{overview,query,investigation}.md`.
4. **Persist learnings** — append generalisable findings to the right
   reference file (see § Memory).

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

When the user passed multiple things (e.g. "give me an overview and then
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

- **Never** run `tshark -V` without `-c 1` or a single-frame filter
  (`-Y 'frame.number == N'`). Full verbose dumps blow up context.
- **Never** pipe an unbounded `tshark -T fields` result into context. Cap at
  200 rows with `head -n 200`; spill the rest to a temp file and report the
  path: `/tmp/analyze-pcap-cache-<sha256-of-input-path>.tsv`.
- **Prefer** the helper scripts in `references/scripts/` over hand-crafted
  filter chains — they are pre-vetted, cache their tshark output, and emit
  compact summaries instead of raw frames.
- **Reuse** the cache: if `/tmp/analyze-pcap-cache-<sha>.tsv` already exists
  for a given pcap and column set, do not re-invoke tshark.
- **AppArmor**: on Ubuntu the Canonical AppArmor profile on tshark restricts
  reads to `/tmp`. The helper scripts auto-stage pcaps into
  `/tmp/analyze-pcap-stage/` — see `references/pcap-format.md` § AppArmor.
- For run directories with multiple UEs, scope tshark queries by UE identifier
  early — the cross-product of 5 pcaps × many UEs is large.

---

## Memory

Two destinations, by kind:

### Generalisable knowledge → `references/` (git-tracked with the skill)

Append after every analysis where something new was learned:

| Kind of finding | Destination |
|---|---|
| Tshark filter that worked, with context for when to use it | `references/tshark-recipes.md` or the relevant `references/protocols/<proto>.md` |
| Procedure failure signature (procedureCode + cause IE pattern) | `references/procedures/<proc>.md` § Accumulated knowledge |
| Upper-PDU framing quirk (dissector binding edge case, DLT detail) | `references/pcap-format.md` |
| New helper script, new flag on an existing script | new file under `references/scripts/`; document invocation in matching `protocols/<proto>.md` § Parsing script |
| Cross-pcap correlation pattern | `references/cross-pcap-correlation.md` |

### Operator/preference knowledge → auto-memory

Write to `/home/xico/.claude/projects/-home-xico-srs-ocudu-ai-playground/memory/`
(via the auto-memory system, not by direct file writes from this skill) when
the user says something that is true *for them* but not generally:

- Preferences: "always check time alignment first", "skip MAC unless asked".
- Local gNB build/version quirks the user calls out.
- Named shortcuts the user invents: "when I say *the usual three*, look at
  ngap+f1ap+e1ap procedure counts".
- Operator conventions: CI run-directory naming, default UE count for a test.

### Never saved anywhere

- Specific RNTI / UE-ID values, frame numbers, run timestamps.
- Root-cause narratives tied to one run.
- KPIs or packet counts observed in a specific capture.
- Anything that only makes sense in the context of one run.

### Maintenance

When the user says **"reorganize pcap knowledge"**:

1. Read all files under `references/`.
2. Dedupe entries; merge entries that belong together.
3. Fix stale tshark syntax for the installed tshark version.
4. Move stray run-specific values out (they should never have been there).
5. Print a one-paragraph summary of what changed.

---

## Activation

This skill lives at `/home/xico/srs/ocudu_ai_playground/skills/analyze-pcap/`.
To activate it under `~/.claude/skills/`, symlink it once:

```bash
ln -s /home/xico/srs/ocudu_ai_playground/skills/analyze-pcap ~/.claude/skills/analyze-pcap
```

Edits in place propagate immediately — no re-install needed.
