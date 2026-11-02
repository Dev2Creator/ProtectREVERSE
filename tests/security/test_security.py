"""Security regression tests: URL validation, archive safety, redaction."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from protectreverse.config import LIMITS
from protectreverse.security import (
    UnsafeTarget,
    find_secrets,
    redact,
    safe_extract_zip,
    validate_public_url,
)


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "ftp://example.com/file",
    "file:///etc/passwd",
    "http://localhost/admin",
    "http://127.0.0.1:8080/",
    "http://[::1]/",
    "http://10.1.2.3/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",
    "https://user:pass@example.com/",
    "http://example.com:8080/",
    "http://printer.local/",
])
def test_rejects_unsafe_urls(url):
    with pytest.raises(UnsafeTarget):
        validate_public_url(url, resolve=False)


def test_accepts_public_https_without_resolution():
    assert validate_public_url("https://example.com/docs", resolve=False).startswith("https://")


def test_redirect_target_is_revalidated():
    from protectreverse.security import validate_redirect

    with pytest.raises(UnsafeTarget):
        validate_redirect("https://example.com/", "http://127.0.0.1/secret")


def test_zip_traversal_is_skipped(tmp_path: Path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escaped.txt", "nope")
        zf.writestr("/absolute.txt", "nope")
        zf.writestr("safe/inside.txt", "ok")

    dest = tmp_path / "out"
    report = safe_extract_zip(archive, dest, LIMITS)

    assert (dest / "safe" / "inside.txt").read_text() == "ok"
    assert not (tmp_path / "escaped.txt").exists()
    assert len(report.skipped) == 2


def test_zip_member_limit_is_enforced(tmp_path: Path):
    archive = tmp_path / "many.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for i in range(5):
            zf.writestr(f"f{i}.txt", "x")
    limits = LIMITS.__class__(max_zip_members=3)
    with pytest.raises(UnsafeTarget):
        safe_extract_zip(archive, tmp_path / "out", limits)


def test_redaction_removes_values_but_keeps_context():
    text = 'API_KEY = "sk_test_abcdefghijklmnop"\nurl = "postgres://user:hunter2@db.example.com/app"'
    cleaned = redact(text)
    assert "sk_test_abcdefghijklmnop" not in cleaned
    assert "hunter2" not in cleaned
    assert "API_KEY" in cleaned  # context preserved, value removed


def test_find_secrets_reports_kinds_only():
    kinds = find_secrets('token = "ghp_' + "a" * 30 + '"')
    assert "github_token" in kinds
    assert all("ghp_" not in kind for kind in kinds)
