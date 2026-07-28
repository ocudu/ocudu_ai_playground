#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Static checks over the skills/ tree.

Catches the failure modes that repeated restructuring introduces and that no
other CI job notices:

1. relative markdown links that don't resolve
2. ${CLAUDE_SKILL_DIR}/... paths that don't exist in the owning skill
3. references to renamed/removed skills
4. one-way layering violations in analyze-ran-log (path links only -- naming an
   artifact kind in prose is explicitly allowed)

Exit 0 when clean, 1 otherwise. stdlib only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"

# Inline markdown links: [text](target). Skips images and reference-style links.
MD_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
# Backtick-quoted relative doc *paths*, e.g. `troubleshooting/handover.md`.
# Requires a slash: a bare `log-format.md` in prose names a doc without claiming
# it sits beside the mentioning file, so it is not a checkable path.
BACKTICK_DOC = re.compile(r"`((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.md)`")
SKILL_DIR_PATH = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/([A-Za-z0-9_./-]+)")

# Skill names that no longer exist -- a leftover reference is a stale pointer.
DEAD_NAMES = ("ran-log-reference", "ran-sherlog", "analyze-pcap", "RAN_LOG_REF_DIR")
# Legacy env var kept as a documented fallback; not a stale pointer.
DEAD_NAME_ALLOW = ("RAN_LOG_REFERENCE_OCUDU_PATH",)

FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
CODE_SPAN = re.compile(r"`[^`\n]*`")

errors: list[str] = []


def rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def strip_fences(text: str) -> str:
    """Drop fenced code blocks -- they hold command and output templates."""
    return FENCE.sub("", text)


def strip_code(text: str) -> str:
    """Drop fenced blocks and inline code spans, leaving only prose."""
    return CODE_SPAN.sub("", strip_fences(text))


def owning_skill(path: Path) -> Path | None:
    """The skills/<name>/ dir containing path, if any."""
    try:
        parts = path.relative_to(SKILLS).parts
    except ValueError:
        return None
    return SKILLS / parts[0] if parts else None


def check_links(md: Path, text: str) -> None:
    # Prose only: a [x](url) inside backticks is an output template, not a link.
    targets = [m.group(1) for m in MD_LINK.finditer(strip_code(text))]
    for target in targets:
        target = target.split("#", 1)[0].strip()
        if not target or "://" in target or target.startswith(("mailto:", "<")):
            continue
        if not (md.parent / target).exists():
            errors.append(f"{rel(md)}: dead link -> {target}")


def check_backtick_docs(md: Path, text: str) -> None:
    """Backtick-quoted .md paths must resolve, relative to the doc or its skill."""
    skill = owning_skill(md)
    for m in BACKTICK_DOC.finditer(strip_fences(text)):
        target = m.group(1)
        # Templated paths (<kind>, <type>, <proto>, <name>) are parametric by design.
        if "<" in target or target.endswith("SKILL.md"):
            continue
        if (md.parent / target).exists():
            continue
        if skill and ((skill / target).exists() or (skill / "references" / target).exists()):
            continue
        errors.append(f"{rel(md)}: unresolved doc reference -> {target}")


def check_skill_dir_paths(md: Path, text: str) -> None:
    skill = owning_skill(md)
    if skill is None:
        return
    for m in SKILL_DIR_PATH.finditer(text):
        target = m.group(1)
        if "<" in target or "*" in target:
            continue
        if not (skill / target).exists():
            errors.append(f"{rel(md)}: ${{CLAUDE_SKILL_DIR}}/{target} does not exist")


def check_dead_names(path: Path, text: str) -> None:
    for line_no, line in enumerate(text.splitlines(), 1):
        for allowed in DEAD_NAME_ALLOW:
            line = line.replace(allowed, "")
        for name in DEAD_NAMES:
            if name in line:
                errors.append(f"{rel(path)}:{line_no}: reference to removed name '{name}'")


SCRIPT_PATH = re.compile(r"scripts/(ocudu|amari-ue|pcap|viavi|correlate)/")


def check_script_layering(md: Path, text: str) -> None:
    """A per-type doc must not reach into another type's scripts/ either."""
    root = SKILLS / "analyze-ran-log" / "references"
    try:
        parts = md.relative_to(root).parts
    except ValueError:
        return
    if len(parts) < 2:
        return
    subtree = parts[0]
    if subtree not in {"ocudu", "amari-ue", "pcap", "viavi"}:
        return
    for m in SCRIPT_PATH.finditer(text):
        other = m.group(1)
        if other != subtree:
            errors.append(
                f"{rel(md)}: per-type doc must not reference scripts/{other}/ "
                f"(route cross-type steps via correlate/)"
            )


def check_layering(md: Path, text: str) -> None:
    """One-way layering inside analyze-ran-log/references/.

    common/ links nothing outward; a per-type subtree never path-links a sibling
    type; nothing links up to a mode-*.md playbook. Prose that merely *names* an
    artifact kind is fine -- only path links count.
    """
    root = SKILLS / "analyze-ran-log" / "references"
    try:
        parts = md.relative_to(root).parts
    except ValueError:
        return
    if len(parts) < 2:  # top-level reference/*.md (playbooks, self-maintenance)
        return
    subtree = parts[0]
    types = {"ocudu", "amari-ue", "pcap", "viavi"}
    # correlate sits *above* the per-type subtrees, so a per-type doc linking into
    # it is an upward reference, not a sibling one.
    upward = {"correlate"}

    prose = strip_fences(text)
    link_targets = [m.group(1).split("#", 1)[0] for m in MD_LINK.finditer(strip_code(text))]
    link_targets += [m.group(1) for m in BACKTICK_DOC.finditer(prose)]

    for target in link_targets:
        norm = target.replace("\\", "/")
        if subtree == "common" and re.search(r"\.\./(ocudu|amari-ue|pcap|viavi|correlate)/", norm):
            errors.append(f"{rel(md)}: common/ must not link outward -> {target}")
        if subtree in types:
            for sibling in types - {subtree}:
                if f"../{sibling}/" in norm or f"../../{sibling}/" in norm:
                    errors.append(
                        f"{rel(md)}: per-type doc must not link sibling type -> {target}"
                    )
            for up in upward:
                if f"../{up}/" in norm or f"../../{up}/" in norm:
                    errors.append(
                        f"{rel(md)}: per-type doc must not link up to {up}/ -> {target}"
                    )
        if re.search(r"mode-(overview|query|investigate)\.md", norm):
            errors.append(f"{rel(md)}: must not link up to a mode playbook -> {target}")


SECTION_CITE = re.compile(r"`([A-Za-z0-9_./-]+\.md)`\s*§\s*([^\n.,;)]+)")


def _headings(path: Path) -> set[str]:
    out = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#"):
            out.add(line.lstrip("#").strip().lower())
    return out


def check_section_cites(md: Path, text: str) -> None:
    """`other.md § Section` must name a heading that exists in other.md."""
    skill = owning_skill(md)
    for m in SECTION_CITE.finditer(strip_fences(text)):
        target, section = m.group(1), m.group(2).strip().lower()
        if "<" in target or target.endswith("SKILL.md"):
            continue
        for cand in (md.parent / target,
                     *( (skill / target, skill / "references" / target) if skill else () )):
            if cand.is_file():
                heads = _headings(cand)
                # The capture can run past the heading into prose, so compare on
                # leading words rather than the whole string.
                def lead(s, n=2):
                    return " ".join(s.split()[:n])
                if not any(section == h or h.startswith(section)
                           or lead(section) == lead(h) for h in heads):
                    errors.append(
                        f"{rel(md)}: cites {target} § {m.group(2).strip()} "
                        f"-- no such heading"
                    )
                break


def main() -> int:
    if not SKILLS.is_dir():
        print(f"no skills/ dir at {SKILLS}", file=sys.stderr)
        return 1

    for path in sorted(SKILLS.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix not in (".md", ".py", ".sh", ".json"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        check_dead_names(path, text)
        if path.suffix == ".md":
            check_links(path, text)
            check_backtick_docs(path, text)
            check_skill_dir_paths(path, text)
            check_layering(path, text)
            check_script_layering(path, text)
            check_section_cites(path, text)

    for path in (REPO / "README.md", REPO / ".claude-plugin" / "marketplace.json"):
        if path.exists():
            check_dead_names(path, path.read_text(encoding="utf-8"))

    # Every skill declared in the marketplace must exist, and vice versa.
    manifest = REPO / ".claude-plugin" / "marketplace.json"
    if manifest.exists():
        import json

        data = json.loads(manifest.read_text(encoding="utf-8"))
        declared = set()
        for plugin in data.get("plugins", []):
            src = REPO / plugin["source"]
            declared.add(plugin["source"].rstrip("/").split("/")[-1])
            if not src.is_dir():
                errors.append(f"marketplace.json: '{plugin['name']}' -> missing {plugin['source']}")
        on_disk = {d.name for d in SKILLS.iterdir() if d.is_dir() and (d / "SKILL.md").exists()}
        for name in sorted(on_disk - declared):
            errors.append(f"marketplace.json: skill '{name}' exists on disk but is not declared")

    if errors:
        print(f"{len(errors)} problem(s):\n")
        for e in errors:
            print(f"  {e}")
        return 1

    print("skill links OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
