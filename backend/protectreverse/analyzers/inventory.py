"""File inventory, language detection and size accounting."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Dict, List

from ..config import LIMITS, TEXT_EXTENSIONS
from ..evidence import Confidence, Status
from .base import AnalysisContext, Analyzer, evidence_for

LANGUAGE_BY_EXT: Dict[str, str] = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby",
    ".php": "PHP", ".c": "C", ".h": "C", ".cc": "C++", ".cpp": "C++", ".hpp": "C++",
    ".cs": "C#", ".swift": "Swift", ".scala": "Scala", ".sh": "Shell", ".sql": "SQL",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "CSS", ".sass": "CSS",
    ".vue": "Vue", ".svelte": "Svelte", ".md": "Markdown", ".rst": "reStructuredText",
    ".json": "JSON", ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML", ".xml": "XML",
}

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
             ".next", ".nuxt", "target", "vendor", ".idea", ".pytest_cache", ".mypy_cache"}


def walk_files(root: Path, max_files: int = LIMITS.max_files) -> List[Path]:
    files: List[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_symlink():
            continue
        if path.is_file():
            files.append(path)
            if len(files) >= max_files:
                break
    return files


def count_lines(path: Path, cap: int = LIMITS.max_text_bytes_scanned) -> int:
    try:
        with open(path, "rb") as handle:
            data = handle.read(cap)
    except OSError:
        return 0
    if b"\x00" in data[:4096]:
        return 0
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


class InventoryAnalyzer(Analyzer):
    name = "inventory"
    category = "structure"

    def analyze(self, ctx: AnalysisContext) -> list:
        files = walk_files(ctx.root)
        ctx.cache["files"] = files

        languages: Counter = Counter()
        loc: Counter = Counter()
        total_bytes = 0
        biggest = []

        for path in files:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            total_bytes += size
            biggest.append((size, path))
            ext = path.suffix.lower()
            language = LANGUAGE_BY_EXT.get(ext)
            if language and ext in TEXT_EXTENSIONS:
                languages[language] += 1
                if language not in {"JSON", "YAML", "TOML", "XML", "Markdown"}:
                    loc[language] += count_lines(path)

        biggest.sort(reverse=True)
        top = [
            {"path": str(p.relative_to(ctx.root)), "bytes": s}
            for s, p in biggest[:5]
        ]
        ctx.cache["languages"] = languages
        ctx.cache["loc"] = loc
        ctx.cache["total_bytes"] = total_bytes

        findings = []
        findings.append(_finding(
            ctx,
            "inventory.size",
            f"{len(files)} files, {total_bytes / 1024 / 1024:.2f} MiB of content",
            Status.OBSERVED, Confidence.HIGH,
            details={"files": len(files), "bytes": total_bytes, "largest": top},
        ))

        if languages:
            summary = ", ".join(f"{name}: {count} files" for name, count in languages.most_common(6))
            findings.append(_finding(
                ctx, "inventory.languages",
                f"Primary file types by count — {summary}",
                Status.OBSERVED, Confidence.HIGH,
                details={"by_files": dict(languages), "loc": dict(loc)},
            ))
        else:
            findings.append(_finding(
                ctx, "inventory.languages",
                "No recognised source-file extensions were found",
                Status.UNKNOWN, Confidence.LOW,
                limitations=["Language detection is extension-based; unusual layouts may be missed"],
            ))

        if total_bytes and biggest and biggest[0][0] > 1024 * 1024:
            findings.append(_finding(
                ctx, "inventory.large_file",
                f"Largest file is {biggest[0][1].name} at {biggest[0][0] / 1024 / 1024:.1f} MiB",
                Status.OBSERVED, Confidence.HIGH,
                evidence=[evidence_for(biggest[0][1], ctx.root)],
                limitations=["A large file is not by itself a problem; it is context for review"],
            ))
        return findings


def _finding(ctx, category, claim, status, confidence, evidence=None, details=None, limitations=None):
    from ..evidence import Finding

    return Finding(
        category=category,
        claim=claim,
        status=status,
        confidence=confidence,
        evidence=evidence or [evidence_for(ctx.root, ctx.root)],
        details=details or {},
        limitations=limitations or [],
    )
