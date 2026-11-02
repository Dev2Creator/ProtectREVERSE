"""Universal intake: local directory, ZIP archive or public Git repository.

Imported code is never executed. Extraction is bounded and traversal-safe.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .config import LIMITS, Limits
from .security import UnsafeTarget, safe_extract_zip, validate_public_url


@dataclass
class Target:
    kind: str                       # "directory" | "archive" | "repository"
    root: Path
    label: str
    meta: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    cleanup: Optional[Path] = None  # temporary extraction root

    def dispose(self) -> None:
        if self.cleanup and self.cleanup.exists():
            shutil.rmtree(self.cleanup, ignore_errors=True)


def _looks_like_git_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and parsed.path.endswith(".git") or value.startswith("https://github.com/")


def open_local(path: Path, limits: Limits = LIMITS) -> Target:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise UnsafeTarget(f"path does not exist: {resolved}")
    if resolved.is_file() and resolved.suffix.lower() == ".zip":
        return open_archive(resolved, limits)
    if not resolved.is_dir():
        raise UnsafeTarget("only directories and .zip archives can be imported")

    file_count = 0
    for _ in resolved.rglob("*"):
        file_count += 1
        if file_count > limits.max_files:
            raise UnsafeTarget(f"project has more than {limits.max_files} entries")
    return Target(kind="directory", root=resolved, label=str(resolved))


def open_archive(path: Path, limits: Limits = LIMITS) -> Target:
    temp_root = Path(tempfile.mkdtemp(prefix="protectreverse-zip-"))
    # Extraction lands in a fresh directory; the original archive is untouched.
    report = safe_extract_zip(path, temp_root, limits)
    target = Target(
        kind="archive",
        root=temp_root,
        label=str(path.resolve()),
        meta={"members": str(report.files), "bytes": str(report.bytes_written)},
        cleanup=temp_root,
    )
    if report.skipped:
        target.warnings.append(f"{len(report.skipped)} archive member(s) skipped for safety")
        target.meta["skipped_examples"] = "; ".join(report.skipped[:3])
    return target


def clone_repository(url: str, limits: Limits = LIMITS) -> Target:
    """Shallow-clone a public repository over HTTPS and pin the revision.

    Only https:// URLs are accepted, and the cloned tree is treated as inert
    data: nothing in it is executed.
    """
    validate_public_url(url)
    if urlparse(url).scheme != "https":
        raise UnsafeTarget("only https repository URLs are supported")

    temp_root = Path(tempfile.mkdtemp(prefix="protectreverse-git-"))
    dest = temp_root / "repo"
    command = [
        "git", "clone", "--depth", "1", "--no-tags",
        "--config", "advice.detachedHead=false",
        url, str(dest),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=180,
            env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/local/bin:/usr/bin:/bin"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise UnsafeTarget(f"clone failed: {exc}") from exc

    if result.returncode != 0:
        shutil.rmtree(temp_root, ignore_errors=True)
        detail = (result.stderr or "").strip().splitlines()[:2]
        raise UnsafeTarget("clone failed: " + (" | ".join(detail) or "unknown git error"))

    revision = _git(dest, "rev-parse", "HEAD")
    subject = _git(dest, "log", "-1", "--format=%s")
    committed = _git(dest, "log", "-1", "--format=%cI")

    return Target(
        kind="repository",
        root=dest,
        label=url,
        meta={
            "revision": revision or "unknown",
            "last_commit_subject": subject or "unknown",
            "last_commit_time": committed or "unknown",
        },
        cleanup=temp_root,
    )


def _git(cwd: Path, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def open_target(value: str, limits: Limits = LIMITS) -> Target:
    """Dispatch a CLI/config value to the right intake adapter."""
    if value.startswith(("http://", "https://")):
        if _looks_like_git_url(value) or value.endswith(".git"):
            return clone_repository(value, limits)
        raise UnsafeTarget(
            "https URLs are only accepted for Git repositories in this release; "
            "website analysis is not implemented yet"
        )
    return open_local(Path(value), limits)
