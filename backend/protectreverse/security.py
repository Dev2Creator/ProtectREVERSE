"""Safety primitives: URL validation, archive extraction, secret redaction.

These are the load-bearing pieces of the platform's security posture. They are
tested directly in tests/security/.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlparse

from .config import Limits


class UnsafeTarget(ValueError):
    """Raised when an input violates the platform's safety rules."""


# --------------------------------------------------------------------------- #
# URL validation / SSRF protection
# --------------------------------------------------------------------------- #

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def resolve_host(host: str) -> List[str]:
    infos = socket.getaddrinfo(host, None)
    return sorted({info[4][0] for info in infos})


def validate_public_url(url: str, *, resolve: bool = True) -> str:
    """Validate a URL for passive, public inspection.

    Rejects non-HTTP schemes, embedded credentials, non-standard ports,
    loopback/private/link-local destinations and hostnames that cannot be
    resolved. Resolution is checked *before* any request is made, and callers
    must re-validate every redirect hop.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeTarget(f"only http and https are allowed, got {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeTarget("URL has no hostname")
    if parsed.username or parsed.password:
        raise UnsafeTarget("embedded credentials are not allowed in a URL")
    if parsed.port not in (None, 80, 443):
        raise UnsafeTarget(f"port {parsed.port} is not allowed")

    host = parsed.hostname.lower().strip(".")
    if host in BLOCKED_HOSTNAMES or host.endswith(".local") or host.endswith(".internal"):
        raise UnsafeTarget(f"hostname {host!r} is not a public destination")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if not _ip_is_public(literal):
            raise UnsafeTarget(f"address {host} is private, loopback or reserved")
        return url

    if not resolve:
        return url

    try:
        addresses = resolve_host(host)
    except socket.gaierror as exc:
        raise UnsafeTarget(f"cannot resolve {host!r}: {exc}") from exc

    if not addresses:
        raise UnsafeTarget(f"{host!r} did not resolve to any address")

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not _ip_is_public(ip):
            raise UnsafeTarget(f"{host!r} resolves to non-public address {address}")
    return url


def validate_redirect(original_url: str, location: str) -> str:
    """Resolve and validate a redirect target before following it."""
    from urllib.parse import urljoin

    target = urljoin(original_url, location)
    return validate_public_url(target)


# --------------------------------------------------------------------------- #
# Archive extraction
# --------------------------------------------------------------------------- #

@dataclass
class ExtractionReport:
    files: int
    bytes_written: int
    skipped: List[str]


def _safe_member_path(root: Path, name: str) -> Optional[Path]:
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return None
    parts = Path(name).parts
    if any(part == ".." for part in parts):
        return None
    if parts and parts[0].startswith(".git"):
        return None
    target = (root / name).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def safe_extract_zip(zip_path: Path, dest: Path, limits: Limits) -> ExtractionReport:
    """Extract a ZIP without traversal, bombs, or symlink escapes."""
    dest.mkdir(parents=True, exist_ok=True)
    skipped: List[str] = []
    written = 0
    count = 0

    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        if len(infos) > limits.max_zip_members:
            raise UnsafeTarget(f"archive has {len(infos)} members, limit is {limits.max_zip_members}")

        total_uncompressed = sum(max(i.file_size, 0) for i in infos)
        if total_uncompressed > limits.max_zip_bytes:
            raise UnsafeTarget("archive expands beyond the configured size limit")

        for info in infos:
            if info.is_dir():
                continue
            count += 1
            if count > limits.max_zip_members:
                raise UnsafeTarget("archive member limit exceeded during extraction")

            target = _safe_member_path(dest, info.filename)
            if target is None:
                skipped.append(f"{info.filename}: unsafe path")
                continue
            if info.file_size > limits.max_file_bytes * 8:
                skipped.append(f"{info.filename}: too large")
                continue
            if info.compress_size > 0 and info.file_size / info.compress_size > limits.max_zip_ratio:
                skipped.append(f"{info.filename}: suspicious compression ratio")
                continue
            if any(p.is_symlink() for p in [target] if p.exists()):
                skipped.append(f"{info.filename}: symlink")
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as sink:
                written += 0
                remaining = limits.max_file_bytes * 8
                while True:
                    chunk = source.read(65536)
                    if not chunk:
                        break
                    written += len(chunk)
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise UnsafeTarget(f"{info.filename} exceeds the per-file limit")
                    sink.write(chunk)

    return ExtractionReport(files=count, bytes_written=written, skipped=skipped)


# --------------------------------------------------------------------------- #
# Secret redaction
# --------------------------------------------------------------------------- #

SECRET_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]{0,4000}?-----END [A-Z ]*PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("assigned_secret", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd|client[_-]?secret)\b\s*[:=]\s*"
        r"['\"]?([A-Za-z0-9_\-./+=]{12,})['\"]?")),
    ("connection_string", re.compile(r"(?i)\b[a-z]+://[^/\s:@]+:[^/\s@]+@[^/\s]+\b")),
)

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Remove secret-shaped substrings. Never returns the raw value."""
    cleaned = text
    for name, pattern in SECRET_PATTERNS:
        if name == "assigned_secret":
            cleaned = pattern.sub(lambda m: f"{m.group(1)}={REDACTED}", cleaned)
        else:
            cleaned = pattern.sub(f"[REDACTED:{name}]", cleaned)
    return cleaned


def find_secrets(text: str) -> List[str]:
    """Return the *kinds* of secret-like strings present, never the values."""
    kinds = []
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            kinds.append(name)
    return kinds


def ensure_inside(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if os.path.commonpath([str(resolved_root), str(resolved)]) != str(resolved_root):
        raise UnsafeTarget(f"{candidate} escapes {root}")
    return resolved
