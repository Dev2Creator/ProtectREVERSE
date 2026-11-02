"""Orchestration for local directory, archive and clone analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from ..config import LIMITS, Limits
from ..evidence import Confidence, Investigation, Status
from ..intake import Target
from .base import AnalysisContext, evidence_for
from .imports import ImportAnalyzer
from .inventory import InventoryAnalyzer
from .manifests import ManifestAnalyzer
from .quality import QualityAnalyzer
from .routes import RoutesAnalyzer
from .tech import TechAnalyzer

ANALYZERS = [
    InventoryAnalyzer(),
    ManifestAnalyzer(),
    ImportAnalyzer(),
    RoutesAnalyzer(),
    QualityAnalyzer(),
    TechAnalyzer(),
]

SCOPE_LIMITS = [
    "Runtime behaviour is not observed: nothing in the project is executed",
    "Deployed infrastructure, private services and databases are out of scope",
    "Dependency vulnerabilities are not checked in this release (no advisory data)",
    "Static analysis cannot see dynamic imports, reflection or generated code",
]


def _readme_summary(root: Path) -> Dict[str, str]:
    for name in ("README.md", "README.rst", "README.txt", "readme.md"):
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        lines = [line.strip() for line in text.splitlines()]
        title = next((l.lstrip("# ").strip() for l in lines if l.startswith("#")), "")
        paragraph = ""
        for line in lines:
            if not line or line.startswith(("#", "!", "[", "<", "|", "-", "=")):
                continue
            if len(line) > 40:
                paragraph = line
                break
        return {"file": name, "title": title, "summary": paragraph}
    return {}


def analyze_target(target: Target, limits: Limits = LIMITS) -> Investigation:
    root = target.root.resolve()
    inv = Investigation(target.label, target.kind, meta=dict(target.meta))
    inv.warnings.extend(target.warnings)

    inv.add_source(
        kind=target.kind,
        label=target.label,
        limitations=["Imported content is treated as untrusted data and is never executed"],
    )
    if target.meta.get("revision"):
        inv.add_source(kind="git-revision", label=f"HEAD {target.meta['revision'][:12]}")

    ctx = AnalysisContext(root=root, label=target.label, kind=target.kind,
                          meta=dict(target.meta), warnings=list(target.warnings))

    for analyzer in ANALYZERS:
        produced: List = analyzer.analyze(ctx)
        for finding in produced:
            inv.add_finding(
                category=finding.category,
                claim=finding.claim,
                status=finding.status,
                confidence=finding.confidence,
                evidence=finding.evidence,
                limitations=finding.limitations,
                details=finding.details,
            )
        if analyzer.name == "manifests":
            declared = next((f.details.get("declared") for f in produced
                             if f.category == "dependencies.declared"), {})
            ctx.cache["declared_dependencies"] = declared or {}
        if analyzer.name == "imports":
            external = next((f.details.get("external_imports") for f in produced
                             if f.category == "architecture.external"), {})
            ctx.cache["external_imports"] = external or {}

    readme = _readme_summary(root)
    if readme.get("summary"):
        inv.add_finding(
            category="overview.purpose",
            claim=f"Project describes itself as: {readme['summary']}",
            status=Status.OBSERVED,
            confidence=Confidence.MEDIUM,
            evidence=[evidence_for(root / readme["file"], ctx.root)],
            limitations=[
                "This is the project's own description, not an independent assessment",
            ],
            details=readme,
        )

    languages = ctx.cache.get("languages") or {}
    loc = ctx.cache.get("loc") or {}
    inv.add_finding(
        category="overview.stack",
        claim="Declared stack summary: " + (
            ", ".join(f"{lang} ({files} files, {loc.get(lang, 0)} lines)"
                      for lang, files in list(languages.items())[:5]) or "undetermined"
        ),
        status=Status.INFERRED,
        confidence=Confidence.MEDIUM,
        details={"languages": dict(languages), "loc": dict(loc)},
        limitations=["Line counts exclude generated, vendored and binary content"],
    )

    inv.add_finding(
        category="scope.not_checked",
        claim="What this investigation does not cover",
        status=Status.NOT_CHECKED,
        confidence=Confidence.HIGH,
        limitations=SCOPE_LIMITS,
        details={"limits": SCOPE_LIMITS},
    )
    return inv
