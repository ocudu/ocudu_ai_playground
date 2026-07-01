# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Shared helpers for the ran-log-reference pcap scripts.

Provides:
- run_tshark(): subprocess wrapper that returns lines from a tshark invocation.
- epoch_to_iso(): format float epoch as ISO-8601 with millisecond precision.
- parse_fields(): split a TSV line into the expected column count.
- walk_run_dir(): map a directory path to its OCUDU pcap siblings.
- cache_path(): deterministic per-session cache path for a (pcap, columns) pair.

All on-disk intermediate state (tshark caches, AppArmor-staged pcaps) lives under
a single per-session directory derived from CLAUDE_CODE_TMPDIR and
CLAUDE_CODE_SESSION_ID. The directory is shared across the artifact types — and,
being session-keyed, reusable by any other skill in the same session — so cached
outputs need not be recomputed. The OS reaps /tmp on reboot — no manual cleanup
needed.
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

# procedureCode -> human name, per protocol. Canonical source is each protocol's
# reference doc § Common procedures and codes (references/protocols/<proto>.md);
# keep this mirror in sync when a code/name there changes. Unknown codes fall
# back to the bare number via proc_name().
PROC_CODE_NAMES: dict[str, dict[int, str]] = {
    "ngap": {
        0: "AMFConfigurationUpdate",
        4: "DownlinkNASTransport",
        14: "InitialContextSetup",
        15: "InitialUEMessage",
        19: "NASNonDeliveryIndication",
        21: "NGSetup",
        24: "Paging",
        28: "PDUSessionResourceRelease",
        29: "PDUSessionResourceSetup",
        35: "RANConfigurationUpdate",
        40: "UEContextModification",
        41: "UEContextRelease",
        44: "UERadioCapabilityInfoIndication",
        46: "UplinkNASTransport",
    },
    "f1ap": {
        1: "F1Setup",
        5: "UEContextSetup",
        6: "UEContextRelease",
        7: "UEContextModification",
        11: "InitialULRRCMessageTransfer",
        12: "DLRRCMessageTransfer",
        13: "ULRRCMessageTransfer",
        26: "F1Removal",
    },
    "e1ap": {
        3: "gNB-CU-UP-E1Setup",
        4: "gNB-CU-CP-E1Setup",
        5: "gNB-CU-UP-ConfigurationUpdate",
        6: "gNB-CU-CP-ConfigurationUpdate",
        7: "E1Release",
        8: "bearerContextSetup",
        9: "bearerContextModification",
        10: "bearerContextModificationRequired",
        11: "bearerContextRelease",
        12: "bearerContextReleaseRequest",
    },
}


def proc_name(proto: str, code: str | int | None, *, with_code: bool = True) -> str:
    """Render a procedureCode as 'Name(code)' (or just 'Name' when with_code=False).

    `proto` is one of ngap/f1ap/e1ap; `code` may be a string (as tshark emits), an
    int, or None/''. With `with_code` (the default) an unknown code renders as the
    bare number, matching the overview/proc-code output; with `with_code=False`
    (used by the per-protocol UE-ID tables) an unknown code renders as 'proc-<n>'
    and an empty code as '?'. This is the single source of procedureCode names —
    keep `PROC_CODE_NAMES` in sync with the protocol reference docs.
    """
    if code is None or code == "":
        return str(code) if with_code else "?"
    try:
        c = int(code)
    except (TypeError, ValueError):
        return str(code)
    name = PROC_CODE_NAMES.get(proto, {}).get(c)
    if name is None:
        return str(c) if with_code else f"proc-{c}"
    return f"{name}({c})" if with_code else name


def to_int(value: str | int | None, base: int = 0) -> int | None:
    """Parse an int from a tshark field value ('0x41', '65', '', None) or None.

    base=0 auto-detects the '0x' prefix tshark emits for hex fields; decimal
    strings parse too. Returns None on empty/unparseable input.
    """
    try:
        return int(str(value), base)
    except (TypeError, ValueError):
        return None


# NAS 5GMM/5GSM message-type code -> name (TS 24.501 §9.7). Protocol-agnostic:
# used wherever tshark reports nas_5gs.mm/sm.message_type (NGAP NAS-PDU and the
# RRC dedicatedNAS-Message carried over F1AP). Unknown codes render as
# "5GMM(0xNN)"/"5GSM(0xNN)". Note: ciphered post-security NAS has no readable
# inner type, so tshark emits no code for it.
NAS_5GMM_TYPES: dict[int, str] = {
    0x41: "RegistrationRequest", 0x42: "RegistrationAccept", 0x43: "RegistrationComplete",
    0x44: "RegistrationReject", 0x45: "DeregistrationRequest(UEorig)",
    0x46: "DeregistrationAccept(UEorig)", 0x47: "DeregistrationRequest(UEterm)",
    0x48: "DeregistrationAccept(UEterm)", 0x4c: "ServiceRequest", 0x4d: "ServiceReject",
    0x4e: "ServiceAccept", 0x54: "ConfigurationUpdateCommand", 0x55: "ConfigurationUpdateComplete",
    0x56: "AuthenticationRequest", 0x57: "AuthenticationResponse", 0x58: "AuthenticationReject",
    0x59: "AuthenticationFailure", 0x5a: "AuthenticationResult", 0x5b: "IdentityRequest",
    0x5c: "IdentityResponse", 0x5d: "SecurityModeCommand", 0x5e: "SecurityModeComplete",
    0x5f: "SecurityModeReject", 0x64: "5GMMStatus", 0x65: "Notification",
    0x66: "NotificationResponse", 0x67: "DLNASTransport", 0x68: "ULNASTransport",
}
NAS_5GSM_TYPES: dict[int, str] = {
    0xc1: "PDUSessionEstablishmentRequest", 0xc2: "PDUSessionEstablishmentAccept",
    0xc3: "PDUSessionEstablishmentReject", 0xc4: "PDUSessionAuthenticationCommand",
    0xc5: "PDUSessionAuthenticationComplete", 0xc6: "PDUSessionAuthenticationResult",
    0xc9: "PDUSessionModificationRequest", 0xca: "PDUSessionModificationReject",
    0xcb: "PDUSessionModificationCommand", 0xcc: "PDUSessionModificationComplete",
    0xcd: "PDUSessionModificationCommandReject", 0xd1: "PDUSessionReleaseRequest",
    0xd2: "PDUSessionReleaseReject", 0xd3: "PDUSessionReleaseCommand",
    0xd4: "PDUSessionReleaseComplete", 0xd6: "5GSMStatus",
}


def nas_name(mm_type: str | int | None, sm_type: str | int | None) -> str | None:
    """Name a NAS message from tshark's reported mm/sm message-type code.

    Prefers the 5GSM (session-management) code when present, else 5GMM. Returns
    None when neither is set (no NAS, or ciphered/undecodable).
    """
    v = to_int(sm_type)
    if v is not None:
        return NAS_5GSM_TYPES.get(v, f"5GSM(0x{v:02x})")
    v = to_int(mm_type)
    if v is not None:
        return NAS_5GMM_TYPES.get(v, f"5GMM(0x{v:02x})")
    return None

# Per-session cache root, shared across the artifact types (and, being
# session-keyed, reusable by any other skill in the same session).
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

    For any read invocation (`-r` present) we enable the MAC-NR / RLC-NR UDP
    heuristic dissectors. OCUDU's mac.pcap / rlc.pcap wrap the NR PDUs in a
    UDP-framed Upper-PDU (frame.protocols = exported_pdu:udp:data); without these
    heuristics (which ship disabled) every `mac-nr.*` / `rlc-nr.*` field and
    `-Y mac-nr`/`-Y rlc-nr` filter silently returns nothing. The flags are inert
    for ngap/f1ap/e1ap captures.
    """
    tshark = require_tshark()
    extra: list[str] = []
    if "-r" in args:
        extra = ["--enable-heuristic", "mac_nr_udp", "--enable-heuristic", "rlc_nr_udp"]
    proc = subprocess.run(
        [tshark, *extra, *args],
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


def filter_valid_fields(
    pcap: str | os.PathLike[str], fields: Iterable[str]
) -> list[str]:
    """Return the subset of `fields` that the local tshark build recognizes.

    tshark rejects the whole `-T fields` query if any `-e` field is unknown, and
    field names vary across Wireshark versions (e.g. -r16 suffixes). Probe once
    (reading a single packet), drop the fields tshark reports as invalid, and
    retry until the set is accepted. Order is preserved.
    """
    staged = stage_for_tshark(pcap)
    remaining = list(fields)
    for _ in range(len(remaining) + 1):
        if not remaining:
            return remaining
        args = ["-r", str(staged), "-T", "fields", "-c", "1"]
        for f in remaining:
            args += ["-e", f]
        try:
            run_tshark(args)
            return remaining
        except TsharkError as e:
            bad = {line.strip() for line in str(e).splitlines()} & set(remaining)
            if not bad:
                raise
            remaining = [f for f in remaining if f not in bad]
    return remaining


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
