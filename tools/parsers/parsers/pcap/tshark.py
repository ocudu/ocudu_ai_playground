# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Running tshark on OCUDU pcaps, with staging of pcaps where tshark can read them and caching of field extractions."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path

# Benign tshark startup warnings about the user's wireshark configuration.
_NOISE_PATTERNS = ("User DLTs Table", "/.config/wireshark/")
# Warnings whose path may follow on the next line.
_NOISE_INTROS = (
    "Can't open your preferences",
    "Could not open your disabled protocols",
    "Could not open your enabled protocols",
    "Could not open your heuristic dissectors",
)
# OCUDU mac.pcap and rlc.pcap wrap NR PDUs in UDP-framed Upper-PDUs, dissected only with these heuristics.
_READ_ARGS = ("--enable-heuristic", "mac_nr_udp", "--enable-heuristic", "rlc_nr_udp")


class TsharkError(RuntimeError):
    """tshark is missing or failed."""


def default_work_dir() -> Path:
    """Directory of staged pcaps and cached extractions when none is given, private to the user."""
    return Path(tempfile.gettempdir()) / f"ocudu-parsers-{os.getuid()}"


def split_fields(line: str, expected: int, sep: str = "\t") -> list[str]:
    """Columns of a tshark "-T fields" line, padded with "" or truncated to the expected count."""
    parts = line.split(sep)
    if len(parts) < expected:
        parts.extend([""] * (expected - len(parts)))
    return parts[:expected]


class Tshark:
    """Runs tshark, staging pcaps and caching field extractions in a work directory.

    on_cache, if given, is called with the cache file and whether it was a hit, for each cached extraction.
    """

    def __init__(self, work_dir: str | os.PathLike[str] | None = None, on_cache: Callable[[Path, bool], None] | None = None):
        self.work_dir = Path(work_dir) if work_dir is not None else default_work_dir()
        self.on_cache = on_cache

    def run(self, args: Sequence[str], *, check: bool = True) -> list[str]:
        """Runs tshark with args, returning its non-empty stdout lines. Raises TsharkError if it fails and check."""
        tshark = shutil.which("tshark")
        if not tshark:
            raise TsharkError("tshark not found on PATH")
        extra = list(_READ_ARGS) if "-r" in args else []
        proc = subprocess.run([tshark, *extra, *args], check=False, capture_output=True, text=True)
        if check and proc.returncode != 0:
            err = _filter_stderr(proc.stderr) or proc.stderr.strip()
            raise TsharkError(f"tshark exited {proc.returncode}: {err}\nargs: {' '.join(args)}")
        return [line for line in proc.stdout.splitlines() if line]

    def version(self) -> str:
        """First line of "tshark -v"."""
        lines = self.run(["-v"])
        return lines[0] if lines else "unknown"

    def stage(self, pcap: str | os.PathLike[str]) -> Path:
        """Returns a path to the pcap that tshark can read: the pcap itself under /tmp, else a link or copy in the
        work directory.
        """
        src = Path(pcap).resolve()
        # The AppArmor profile of tshark on Ubuntu only lets it read under /tmp and a few system paths.
        if str(src).startswith("/tmp/"):
            return src
        digest = hashlib.sha256(str(src).encode()).hexdigest()[:16]
        stage_dir = self.work_dir / "pcap-stage"
        stage_dir.mkdir(parents=True, exist_ok=True)
        staged = stage_dir / f"{digest}-{src.name}"
        if staged.exists():
            try:
                if staged.stat().st_mtime >= src.stat().st_mtime:
                    return staged
            except FileNotFoundError:
                pass
            staged.unlink(missing_ok=True)
        try:
            os.link(src, staged)
        except OSError:
            shutil.copy2(src, staged)
        return staged

    def valid_fields(self, pcap: str | os.PathLike[str], fields: Iterable[str]) -> list[str]:
        """The fields that this tshark build knows, in order."""
        staged = self.stage(pcap)
        remaining = list(fields)
        # tshark rejects a query with any unknown field, naming the unknown ones, and names vary across versions.
        for _ in range(len(remaining) + 1):
            if not remaining:
                return remaining
            args = ["-r", str(staged), "-T", "fields", "-c", "1"]
            for f in remaining:
                args += ["-e", f]
            try:
                self.run(args)
                return remaining
            except TsharkError as e:
                bad = {line.strip() for line in str(e).splitlines()} & set(remaining)
                if not bad:
                    raise
                remaining = [f for f in remaining if f not in bad]
        return remaining

    def cache_path(self, pcap: str | os.PathLike[str], tag: str) -> Path:
        """Cache file of an extraction from a pcap, identified by tag."""
        canonical = str(Path(pcap).resolve())
        digest = hashlib.sha256(f"{canonical}\0{tag}".encode()).hexdigest()[:16]
        return self.work_dir / f"pcap-cache-{digest}.tsv"

    def iter_fields(
        self,
        pcap: str | os.PathLike[str],
        fields: Iterable[str],
        *,
        display_filter: str | None = None,
        tag: str | None = None,
        force: bool = False,
    ) -> Iterator[list[str]]:
        """Yields the values of fields for each frame matching display_filter, as strings, "" when absent.

        Extractions are cached under tag, by default the fields and filter. force runs tshark even on a cache hit.
        """
        fields_list = list(fields)
        tag_str = tag or "+".join(fields_list) + ("|" + display_filter if display_filter else "")
        cf = self.cache_path(pcap, tag_str)
        hit = cf.exists() and not force
        if self.on_cache is not None:
            self.on_cache(cf, hit)
        if hit:
            with cf.open() as fh:
                for line in fh:
                    line = line.rstrip("\n")
                    if line:
                        yield split_fields(line, len(fields_list))
            return
        args = ["-r", str(self.stage(pcap)), "-T", "fields", "-E", "separator=\t"]
        for f in fields_list:
            args += ["-e", f]
        if display_filter:
            args += ["-Y", display_filter]
        lines = self.run(args)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text("\n".join(lines) + ("\n" if lines else ""))
        for line in lines:
            yield split_fields(line, len(fields_list))


def _filter_stderr(stderr: str) -> str:
    """tshark stderr without the benign wireshark configuration warnings."""
    keep: list[str] = []
    skip_next = False
    for line in stderr.splitlines():
        if skip_next:
            skip_next = False
            continue
        if any(p in line for p in _NOISE_INTROS):
            skip_next = True
            continue
        if any(p in line for p in _NOISE_PATTERNS):
            continue
        keep.append(line)
    return "\n".join(keep).strip()
