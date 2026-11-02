"""API route extraction from common web frameworks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from ..evidence import Confidence, Finding, Status
from .base import AnalysisContext, Analyzer, evidence_for

PATTERNS = (
    ("FastAPI", re.compile(r"@(?P<obj>\w+)\.(?P<method>get|post|put|patch|delete)\(\s*['\"](?P<path>[^'\"]+)['\"]")),
    ("Flask", re.compile(r"@(?P<obj>\w+)\.route\(\s*['\"](?P<path>[^'\"]+)['\"]")),
    ("Django", re.compile(r"\bpath\(\s*['\"](?P<path>[^'\"]+)['\"]")),
    ("Express", re.compile(r"\b(?:app|router)\.(?P<method>get|post|put|patch|delete)\(\s*['\"](?P<path>[^'\"]+)['\"]")),
)

SOURCE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx"}


class RoutesAnalyzer(Analyzer):
    name = "routes"
    category = "api"

    def analyze(self, ctx: AnalysisContext) -> List[Finding]:
        endpoints: List[dict] = []
        frameworks: set = set()

        for path in ctx.cache.get("files", []):
            if path.suffix not in SOURCE_EXT:
                continue
            try:
                lines = path.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, start=1):
                for framework, pattern in PATTERNS:
                    match = pattern.search(line)
                    if not match:
                        continue
                    groups = match.groupdict()
                    methods = _methods_for(line, groups.get("method"))
                    for method in methods:
                        endpoints.append({
                            "framework": framework,
                            "method": method,
                            "path": groups["path"],
                            "file": str(path.relative_to(ctx.root)),
                            "line": number,
                        })
                    frameworks.add(framework)

        if not endpoints:
            return [Finding(
                category="api.routes",
                claim="No HTTP route declarations were detected in source files",
                status=Status.UNKNOWN,
                confidence=Confidence.LOW,
                evidence=[evidence_for(ctx.root, ctx.root)],
                limitations=[
                    "Routes registered dynamically, generated, or declared in an unsupported framework are invisible here",
                ],
            )]

        by_framework = ", ".join(sorted(frameworks))
        findings = [Finding(
            category="api.routes",
            claim=f"{len(endpoints)} HTTP endpoint declaration(s) detected ({by_framework})",
            status=Status.OBSERVED,
            confidence=Confidence.HIGH,
            evidence=[
                evidence_for(ctx.root / e["file"], ctx.root, lines=str(e["line"]))
                for e in endpoints[:3]
            ],
            details={
                "endpoints": endpoints[:200],
                "by_method": _count(endpoints, "method"),
                "frameworks": sorted(frameworks),
            },
            limitations=[
                "Static patterns miss routers mounted elsewhere, middleware-only routes and generated route tables",
                "Detected declarations do not prove the routes are reachable or enabled at runtime",
            ],
        )]

        paths = sorted({e["path"] for e in endpoints})
        if paths:
            findings.append(Finding(
                category="api.surface",
                claim="Documented path prefixes in code: " + ", ".join(paths[:12]),
                status=Status.OBSERVED,
                confidence=Confidence.MEDIUM,
                evidence=[evidence_for(ctx.root / endpoints[0]["file"], ctx.root,
                                      lines=str(endpoints[0]["line"]))],
                details={"paths": paths[:200]},
            ))
        return findings


METHODS_LIST = re.compile(r"methods\s*=\s*\[([^\]]*)\]")


def _methods_for(line: str, explicit_method: str | None) -> List[str]:
    """Flask-style decorators carry the methods in a list argument."""
    if explicit_method:
        return [explicit_method.upper()]
    match = METHODS_LIST.search(line)
    if match:
        methods = [m.strip(" '\"") .upper() for m in match.group(1).split(",") if m.strip(" '\"")]
        return methods or ["GET"]
    return ["GET"]


def _count(items: List[dict], key: str) -> dict:
    result: dict = {}
    for item in items:
        value = item.get(key, "?")
        result[value] = result.get(value, 0) + 1
    return result
