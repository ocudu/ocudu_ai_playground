"""Shared helpers for analyze-pcap scripts.

Provides:
- run_tshark(): subprocess wrapper that returns lines from a tshark invocation.
- epoch_to_iso(): format float epoch as ISO-8601 with millisecond precision.
- parse_fields(): split a TSV line into the expected column count.
- walk_run_dir(): map a directory path to its OCUDU pcap siblings.
- cache_path(): deterministic per-session cache path for a (pcap, columns) pair.

All on-disk intermediate state (tshark caches, AppArmor-staged pcaps) lives under
a single per-session directory derived from CLAUDE_CODE_TMPDIR and
CLAUDE_CODE_SESSION_ID. The directory is shared with the analyze-amari-ue-log
skill so both can cross-reference cached outputs in one run. The OS reaps /tmp on
reboot — no manual cleanup needed.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Iterator, Sequence

PCAP_NAMES = ("mac.pcap", "rlc.pcap", "f1ap.pcap", "e1ap.pcap", "ngap.pcap")

# Per-session cache root, shared with the analyze-amari-ue-log skill.
# CLAUDE_CODE_TMPDIR (e.g. /tmp/claude-1000) is the per-user tmpdir Claude Code
# sets up with 0700 perms; nesting our session dir inside it inherits that
# privacy. CLAUDE_CODE_SESSION_ID isolates concurrent sessions on the same box.
_CACHE_ROOT = (
    Path(os.environ.get("CLAUDE_CODE_TMPDIR", "/tmp"))
    / f"claude-skills-{os.environ.get('CLAUDE_CODE_SESSION_ID', 'default')}"
)
_TSHARK_STAGE_DIR = _CACHE_ROOT / "pcap-stage"


class TsharkError(RuntimeError):
    pass


def require_tshark() -> str:
    """Return the path to tshark or raise."""
    path = shutil.which("tshark")
    if not path:
        raise TsharkError("tshark not found on PATH")
    return path


def stage_for_tshark(pcap_path: str | os.PathLike[str]) -> Path:
    """Stage a pcap in /tmp so the Canonical AppArmor profile on tshark can read it.

    Canonical ships an AppArmor profile (/etc/apparmor.d/tshark) that restricts
    /usr/bin/tshark to /tmp and a few system paths. Files under ~/srs/ etc.
    trigger "You don't have permission to read the file" even when Unix perms
    allow it. Hard-link (or copy on a different fs) into the per-session
    pcap-stage/ subdir (see _CACHE_ROOT), keyed by canonical source path sha +
    basename.

    If the source is already under /tmp (likely already accessible), pass it
    through unchanged.
    """
    src = Path(pcap_path).resolve()
    if str(src).startswith("/tmp/"):
        return src
    digest = hashlib.sha256(str(src).encode()).hexdigest()[:16]
    _TSHARK_STAGE_DIR.mkdir(parents=True, exist_ok=True)
    staged = _TSHARK_STAGE_DIR / f"{digest}-{src.name}"
    if staged.exists():
        try:
            if staged.stat().st_mtime >= src.stat().st_mtime:
                return staged
        except FileNotFoundError:
            pass
        try:
            staged.unlink()
        except FileNotFoundError:
            pass
    try:
        os.link(src, staged)
    except OSError:
        shutil.copy2(src, staged)
    return staged


_NOISE_PATTERNS = (
    "User DLTs Table",
    "/.config/wireshark/",
)

_NOISE_INTROS = (
    "Can't open your preferences",
    "Could not open your disabled protocols",
    "Could not open your enabled protocols",
    "Could not open your heuristic dissectors",
)


def _filter_tshark_stderr(stderr: str) -> str:
    """Drop benign tshark startup noise (wireshark config permission warnings).

    Real errors — including "You don't have permission to read the file" for the
    target pcap, "Some fields aren't valid", etc. — are preserved.
    """
    keep: list[str] = []
    skip_next = False
    for line in stderr.splitlines():
        if skip_next:
            skip_next = False
            continue
        if any(p in line for p in _NOISE_INTROS):
            # Path follows on the next line in some tshark builds; skip it too.
            skip_next = True
            continue
        if any(p in line for p in _NOISE_PATTERNS):
            continue
        keep.append(line)
    return "\n".join(keep).strip()


def run_tshark(args: Sequence[str], *, check: bool = True) -> list[str]:
    """Run tshark with the given args and return stdout lines (no trailing newlines).

    Benign wireshark-config permission warnings are filtered from any raised
    TsharkError so the real cause is visible.
    """
    tshark = require_tshark()
    proc = subprocess.run(
        [tshark, *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        err = _filter_tshark_stderr(proc.stderr) or proc.stderr.strip()
        raise TsharkError(
            f"tshark exited {proc.returncode}: {err}\n"
            f"args: {' '.join(args)}"
        )
    return [line for line in proc.stdout.splitlines() if line]


def epoch_to_iso(epoch: float | str) -> str:
    """Format an epoch (seconds, may be float or string) as ISO-8601 with ms.

    Uses UTC. No trailing Z (the user prefers the bare form).
    """
    try:
        ts = float(epoch)
    except (TypeError, ValueError):
        return str(epoch)
    dt = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


def parse_fields(line: str, expected: int, sep: str = "\t") -> list[str]:
    """Split a TSV line into exactly `expected` columns.

    Pads short rows with '' and truncates long ones. tshark `-T fields` output
    shouldn't contain embedded tabs in a single field value, so silently
    truncating extras is safe.
    """
    parts = line.split(sep)
    if len(parts) < expected:
        parts.extend([""] * (expected - len(parts)))
    elif len(parts) > expected:
        parts = parts[:expected]
    return parts


def walk_run_dir(path: str | os.PathLike[str]) -> dict[str, Path | None]:
    """Map a directory to its OCUDU sibling pcaps.

    Returns a dict like {"mac": Path|None, "rlc": Path|None, ...}.
    """
    p = Path(path)
    if not p.is_dir():
        raise FileNotFoundError(f"not a directory: {p}")
    out: dict[str, Path | None] = {}
    for name in PCAP_NAMES:
        full = p / name
        out[name.split(".")[0]] = full if full.is_file() else None
    return out


def is_run_dir(path: str | os.PathLike[str]) -> bool:
    """Return True if a directory contains at least two known OCUDU pcaps."""
    p = Path(path)
    if not p.is_dir():
        return False
    present = sum(1 for n in PCAP_NAMES if (p / n).is_file())
    return present >= 2


def cache_path(input_path: str | os.PathLike[str], tag: str) -> Path:
    """Return a deterministic cache path inside the per-session cache root.

    File: pcap-cache-<sha>.tsv under _CACHE_ROOT. Callers must ensure the parent
    directory exists before writing (iter_fields_cached does this).
    """
    canonical = str(Path(input_path).resolve())
    digest = hashlib.sha256(f"{canonical}\0{tag}".encode()).hexdigest()[:16]
    return _CACHE_ROOT / f"pcap-cache-{digest}.tsv"


def iter_fields_cached(
    pcap: str | os.PathLike[str],
    fields: Iterable[str],
    *,
    display_filter: str | None = None,
    tag: str | None = None,
    force: bool = False,
) -> Iterator[list[str]]:
    """Yield rows of the requested tshark fields, caching to /tmp.

    Pass force=True to bypass the cache (will still write a fresh cache file).
    """
    fields_list = list(fields)
    tag_str = tag or "+".join(fields_list) + ("|" + display_filter if display_filter else "")
    cf = cache_path(pcap, tag_str)
    if cf.exists() and not force:
        with cf.open() as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line:
                    continue
                yield parse_fields(line, len(fields_list))
        return
    staged = stage_for_tshark(pcap)
    args = ["-r", str(staged), "-T", "fields", "-E", "separator=\t"]
    for f in fields_list:
        args += ["-e", f]
    if display_filter:
        args += ["-Y", display_filter]
    lines = run_tshark(args)
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text("\n".join(lines) + ("\n" if lines else ""))
    for line in lines:
        yield parse_fields(line, len(fields_list))


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)
