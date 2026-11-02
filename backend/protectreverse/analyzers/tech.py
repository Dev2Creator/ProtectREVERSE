"""Technology fingerprinting with explicit confidence levels."""

from __future__ import annotations

from typing import Dict, List, Set

from ..evidence import Confidence, Finding, Status
from .base import AnalysisContext, Analyzer, evidence_for

# dependency / import name -> (display name, kind)
KNOWN_TECH: Dict[str, tuple] = {
    "flask": ("Flask", "web framework"),
    "fastapi": ("FastAPI", "web framework"),
    "django": ("Django", "web framework"),
    "starlette": ("Starlette", "ASGI toolkit"),
    "express": ("Express", "web framework"),
    "koa": ("Koa", "web framework"),
    "next": ("Next.js", "frontend framework"),
    "react": ("React", "frontend library"),
    "vue": ("Vue", "frontend framework"),
    "svelte": ("Svelte", "frontend framework"),
    "angular": ("Angular", "frontend framework"),
    "spring-boot": ("Spring Boot", "application framework"),
    "rails": ("Ruby on Rails", "web framework"),
    "laravel": ("Laravel", "web framework"),
    "gin": ("Gin", "web framework"),
    "actix-web": ("Actix", "web framework"),
    "sqlalchemy": ("SQLAlchemy", "ORM"),
    "prisma": ("Prisma", "ORM"),
    "sequelize": ("Sequelize", "ORM"),
    "mongoose": ("Mongoose", "ODM"),
    "torch": ("PyTorch", "ML framework"),
    "tensorflow": ("TensorFlow", "ML framework"),
    "numpy": ("NumPy", "scientific computing"),
    "pandas": ("pandas", "data analysis"),
    "pytest": ("pytest", "testing"),
    "jest": ("Jest", "testing"),
    "vite": ("Vite", "build tool"),
    "webpack": ("webpack", "build tool"),
}


class TechAnalyzer(Analyzer):
    name = "tech"
    category = "technology"

    def analyze(self, ctx: AnalysisContext) -> List[Finding]:
        declared: Set[str] = set()
        imported: Set[str] = set()

        for manifest_deps in (ctx.cache.get("declared_dependencies") or {}).values():
            declared.update(name.lower() for name in manifest_deps)

        for name in (ctx.cache.get("external_imports") or {}):
            imported.add(name.lower())

        findings: List[Finding] = []
        seen = set()

        for key in sorted(declared | imported):
            base = key.split("/")[0].split("-")[0]
            tech = KNOWN_TECH.get(key) or KNOWN_TECH.get(base)
            if not tech or tech[0] in seen:
                continue
            seen.add(tech[0])
            both = key in declared and key in imported
            confidence = Confidence.HIGH if both else Confidence.MEDIUM
            evidence_kind = "declared dependency and imported" if both else (
                "declared dependency" if key in declared else "imported in source")
            findings.append(Finding(
                category="technology.fingerprint",
                claim=f"{tech[0]} detected ({tech[1]}) — evidence: {evidence_kind}",
                status=Status.OBSERVED if both else Status.INFERRED,
                confidence=confidence,
                evidence=[evidence_for(ctx.root, ctx.root, excerpt=f"{key}: {evidence_kind}")],
                details={"technology": tech[0], "kind": tech[1], "name": key},
                limitations=[
                    "A manifest entry does not prove the technology runs in production",
                    "Only listed technologies are fingerprinted in this release",
                ],
            ))
            if len(findings) >= 8:
                break

        if not findings:
            findings.append(Finding(
                category="technology.fingerprint",
                claim="No fingerprints matched the technologies this release knows about",
                status=Status.UNKNOWN,
                confidence=Confidence.LOW,
                evidence=[evidence_for(ctx.root, ctx.root)],
                limitations=["Absence of a match is not evidence that no framework is used"],
            ))
        return findings
