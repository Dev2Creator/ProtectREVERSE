"""Package manifests and declared dependencies."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Dict, List

from ..evidence import Confidence, Finding, Status
from .base import AnalysisContext, Analyzer, evidence_for

REQ_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*([<>=!~]=?\s*[^;#]*)?")
GO_REQUIRE = re.compile(r"^\s*([\w./\-]+)\s+v[\w.\-+]+\s*$")
POM_ARTIFACT = re.compile(r"<artifactId>([^<]+)</artifactId>")


class ManifestAnalyzer(Analyzer):
    name = "manifests"
    category = "dependencies"

    def analyze(self, ctx: AnalysisContext) -> List[Finding]:
        findings: List[Finding] = []
        declared: Dict[str, Dict[str, str]] = {}
        manifests_found: List[str] = []

        for path in ctx.cache.get("files", []):
            name = path.name
            try:
                if name.startswith("requirements") and name.endswith(".txt"):
                    deps = self._requirements(path)
                    manifests_found.append(name)
                    declared.setdefault("requirements.txt", {}).update(deps)
                elif name == "package.json":
                    deps = self._package_json(path)
                    manifests_found.append(name)
                    declared.setdefault("package.json", {}).update(deps)
                elif name == "pyproject.toml":
                    deps = self._pyproject(path)
                    manifests_found.append(name)
                    declared.setdefault("pyproject.toml", {}).update(deps)
                elif name == "go.mod":
                    deps = self._go_mod(path)
                    manifests_found.append(name)
                    declared.setdefault("go.mod", {}).update(deps)
                elif name == "pom.xml":
                    deps = self._pom(path)
                    manifests_found.append(name)
                    declared.setdefault("pom.xml", {}).update(deps)
            except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
                findings.append(Finding(
                    category="dependencies.parse_error",
                    claim=f"{name} could not be parsed",
                    status=Status.NOT_CHECKED,
                    confidence=Confidence.LOW,
                    evidence=[evidence_for(path, ctx.root)],
                    limitations=[f"parser error: {type(exc).__name__}"],
                ))

        total = sum(len(v) for v in declared.values())
        if manifests_found:
            sample = ", ".join(sorted(manifests_found)[:6])
            findings.append(Finding(
                category="dependencies.declared",
                claim=f"{total} declared dependency entries across {len(manifests_found)} manifest(s): {sample}",
                status=Status.OBSERVED,
                confidence=Confidence.HIGH,
                evidence=[evidence_for(ctx.root / manifests_found[0], ctx.root)],
                details={"manifests": sorted(manifests_found), "declared": declared},
                limitations=[
                    "A declared dependency is not proof it is imported or used",
                    "Transitive dependencies are only visible when a lockfile is present",
                ],
            ))
        else:
            findings.append(Finding(
                category="dependencies.declared",
                claim="No supported package manifest was found",
                status=Status.UNKNOWN,
                confidence=Confidence.LOW,
                evidence=[evidence_for(ctx.root, ctx.root)],
                limitations=["Projects without manifests may vendor dependencies or use an unsupported format"],
            ))

        lockfiles = [
            p.name for p in ctx.cache.get("files", [])
            if p.name in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
                          "Pipfile.lock", "go.sum", "Cargo.lock", "composer.lock", "Gemfile.lock"}
        ]
        if manifests_found and not lockfiles:
            findings.append(Finding(
                category="dependencies.lockfile",
                claim="Dependency manifests exist but no lockfile was found",
                status=Status.INFERRED,
                confidence=Confidence.MEDIUM,
                evidence=[evidence_for(ctx.root, ctx.root)],
                limitations=["Some projects pin versions directly in the manifest instead of a lockfile"],
            ))
        elif lockfiles:
            findings.append(Finding(
                category="dependencies.lockfile",
                claim=f"Lockfile(s) present: {', '.join(sorted(lockfiles))}",
                status=Status.OBSERVED,
                confidence=Confidence.HIGH,
                evidence=[evidence_for(ctx.root / lockfiles[0], ctx.root)],
                details={"lockfiles": sorted(lockfiles)},
            ))
        return findings

    # -- per-format parsers -------------------------------------------------
    def _requirements(self, path: Path) -> Dict[str, str]:
        deps: Dict[str, str] = {}
        for line in path.read_text(errors="replace").splitlines():
            if not line.strip() or line.strip().startswith(("#", "-")):
                continue
            match = REQ_LINE.match(line)
            if match:
                deps[match.group(1)] = (match.group(2) or "").strip()
        return deps

    def _package_json(self, path: Path) -> Dict[str, str]:
        data = json.loads(path.read_text(errors="replace"))
        deps: Dict[str, str] = {}
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            for name, version in (data.get(key) or {}).items():
                deps[name] = str(version)
        return deps

    def _pyproject(self, path: Path) -> Dict[str, str]:
        data = tomllib.loads(path.read_text(errors="replace"))
        deps: Dict[str, str] = {}
        project = data.get("project", {})
        for entry in project.get("dependencies", []) or []:
            name = re.split(r"[<>=!~\[ ]", entry, maxsplit=1)[0].strip()
            if name:
                deps[name] = entry[len(name):].strip()
        poetry = data.get("tool", {}).get("poetry", {})
        for name, spec in (poetry.get("dependencies") or {}).items():
            if name.lower() != "python":
                deps[name] = str(spec)
        return deps

    def _go_mod(self, path: Path) -> Dict[str, str]:
        deps: Dict[str, str] = {}
        for line in path.read_text(errors="replace").splitlines():
            match = GO_REQUIRE.match(line)
            if match:
                deps[match.group(1)] = "required"
        return deps

    def _pom(self, path: Path) -> Dict[str, str]:
        text = path.read_text(errors="replace")
        return {artifact: "maven" for artifact in POM_ARTIFACT.findall(text)}
