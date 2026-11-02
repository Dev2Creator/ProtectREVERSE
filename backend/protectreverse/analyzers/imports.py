"""Module import graph and entry-point discovery (read-only, no execution)."""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set

from ..evidence import Confidence, Finding, Status
from .base import AnalysisContext, Analyzer, evidence_for

JS_IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\))""")

ENTRY_CANDIDATES = {"main.py", "app.py", "manage.py", "cli.py", "__main__.py", "run.py",
                    "server.py", "index.js", "index.ts", "server.js", "main.go",
                    "main.rs", "Program.cs", "Main.java"}


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = [p for p in rel.parts if p not in {"__init__"}]
    return ".".join(parts) if parts else path.stem


def resolve_local(module: str, local_by_name: Dict[str, Path]) -> str | None:
    """Map an import string to a module that exists in this project.

    Exact matches win. Otherwise the shallowest module inside the named
    package is returned, which is what ``import pkg`` means when ``pkg`` is a
    namespace-style directory. Returns ``None`` when nothing local matches.
    """
    if not module:
        return None
    if module in local_by_name:
        return module
    candidates = [name for name in local_by_name if name.startswith(module + ".")]
    if not candidates:
        return None
    return min(candidates, key=len)


def module_package(source: str) -> List[str]:
    """The package parts that a relative import at ``source`` resolves against."""
    parts = source.split(".") if source else []
    return parts[:-1] if len(parts) > 1 else []


def relative_target(source: str, level: int, module: str | None) -> str:
    """Resolve ``from ...module import x`` to an absolute module name."""
    base = module_package(source)
    for _ in range(max(level - 1, 0)):
        if base:
            base = base[:-1]
    if module:
        base = base + module.split(".")
    return ".".join(base)


def find_cycles(edges: Dict[str, Set[str]], limit: int = 20) -> List[List[str]]:
    """Enumerate simple cycles (bounded) so circular imports can be reported."""
    cycles: List[List[str]] = []
    seen: Set[tuple] = set()

    def walk(start: str, node: str, path: List[str], stack: Set[str]) -> None:
        if len(cycles) >= limit:
            return
        for nxt in sorted(edges.get(node, ())):
            if nxt == start and len(path) >= 2:
                key = tuple(sorted(path))
                if key not in seen:
                    seen.add(key)
                    cycles.append(list(path))
            elif nxt not in stack and len(path) < 12:
                stack.add(nxt)
                path.append(nxt)
                walk(start, nxt, path, stack)
                path.pop()
                stack.discard(nxt)

    for node in sorted(edges):
        walk(node, node, [node], {node})
    return cycles


class ImportAnalyzer(Analyzer):
    name = "imports"
    category = "architecture"

    def analyze(self, ctx: AnalysisContext) -> List[Finding]:
        files: List[Path] = ctx.cache.get("files", [])
        local_by_name: Dict[str, Path] = {}

        for path in files:
            if path.suffix == ".py":
                local_by_name[_module_name(path, ctx.root)] = path

        edges: Dict[str, Set[str]] = defaultdict(set)
        external: Counter = Counter()
        parse_problems: List[str] = []
        unresolved_relative: List[str] = []

        for path in files:
            if path.suffix == ".py":
                self._python_edges(path, ctx, local_by_name, edges, external,
                                   parse_problems, unresolved_relative)
            elif path.suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
                self._js_edges(path, ctx, edges, external)

        fan_in = Counter()
        for source, targets in edges.items():
            for target in targets:
                fan_in[target] += 1

        findings: List[Finding] = []
        if edges:
            hubs = fan_in.most_common(5)
            findings.append(Finding(
                category="architecture.imports",
                claim=(
                    "Internal module graph built from "
                    f"{len(edges)} module(s) with {sum(len(v) for v in edges.values())} local edge(s); "
                    "most imported modules: " + ", ".join(f"{name} ({count})" for name, count in hubs)
                ),
                status=Status.OBSERVED,
                confidence=Confidence.MEDIUM,
                evidence=[evidence_for(local_by_name.get(hubs[0][0], ctx.root), ctx.root) if hubs else evidence_for(ctx.root, ctx.root)],
                details={
                    "edges": {k: sorted(v) for k, v in sorted(edges.items())[:200]},
                    "fan_in": dict(fan_in.most_common(20)),
                },
                limitations=[
                    "Python imports are resolved only for modules inside this project",
                    "Dynamic imports, aliasing and runtime loader tricks are not visible statically",
                ],
            ))
        else:
            findings.append(Finding(
                category="architecture.imports",
                claim="No internal import relationships could be resolved",
                status=Status.UNKNOWN,
                confidence=Confidence.LOW,
                evidence=[evidence_for(ctx.root, ctx.root)],
            ))

        if external:
            top = ", ".join(f"{name} ({count})" for name, count in external.most_common(8))
            findings.append(Finding(
                category="architecture.external",
                claim=f"Most imported external packages: {top}",
                status=Status.OBSERVED,
                confidence=Confidence.HIGH,
                evidence=[evidence_for(ctx.root, ctx.root)],
                details={"external_imports": dict(external.most_common(40))},
                limitations=["An import shows a name is referenced, not how much it matters at runtime"],
            ))

        cycles = find_cycles({k: set(v) for k, v in edges.items()})
        if cycles:
            findings.append(Finding(
                category="architecture.cycles",
                claim=f"{len(cycles)} circular import chain(s) detected",
                status=Status.OBSERVED,
                confidence=Confidence.HIGH,
                evidence=[evidence_for(local_by_name.get(cycles[0][0], ctx.root), ctx.root)],
                details={"cycles": cycles},
                limitations=[
                    "Only static imports inside this project are considered",
                    "A cycle is not automatically a defect, but it complicates testing and refactoring",
                ],
            ))

        if unresolved_relative:
            findings.append(Finding(
                category="architecture.unresolved_imports",
                claim=f"{len(unresolved_relative)} relative import(s) did not resolve to a project module",
                status=Status.INFERRED,
                confidence=Confidence.LOW,
                evidence=[evidence_for(ctx.root, ctx.root)],
                details={"unresolved": unresolved_relative[:20]},
                limitations=["Dynamic module creation and generated files are invisible to static parsing"],
            ))

        entries = [p for p in files if p.name in ENTRY_CANDIDATES]
        if entries:
            findings.append(Finding(
                category="architecture.entry_points",
                claim="Candidate entry points: " + ", ".join(str(p.relative_to(ctx.root)) for p in entries[:8]),
                status=Status.INFERRED,
                confidence=Confidence.MEDIUM,
                evidence=[evidence_for(p, ctx.root) for p in entries[:3]],
                details={"entry_points": [str(p.relative_to(ctx.root)) for p in entries]},
                limitations=["Filename heuristics can miss the real entry point or include unused scripts"],
            ))
        else:
            findings.append(Finding(
                category="architecture.entry_points",
                claim="No conventional entry-point filename was found",
                status=Status.UNKNOWN,
                confidence=Confidence.LOW,
                evidence=[evidence_for(ctx.root, ctx.root)],
            ))

        if parse_problems:
            findings.append(Finding(
                category="architecture.parse",
                claim=f"{len(parse_problems)} Python file(s) could not be parsed",
                status=Status.NOT_CHECKED,
                confidence=Confidence.LOW,
                evidence=[evidence_for(ctx.root / parse_problems[0], ctx.root)],
                limitations=parse_problems[:5],
            ))
        return findings

    # ------------------------------------------------------------------ #
    def _python_edges(self, path: Path, ctx, local_by_name, edges, external, problems,
                      unresolved_relative) -> None:
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            problems.append(str(path.relative_to(ctx.root)))
            return

        source = _module_name(path, ctx.root)
        edges.setdefault(source, set())

        def add(target: str | None) -> bool:
            if target:
                edges[source].add(target)
                return True
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if add(resolve_local(alias.name, local_by_name)):
                        continue
                    base = alias.name.split(".")[0]
                    if add(resolve_local(base, local_by_name)):
                        continue
                    external[base] += 1

            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    target = relative_target(source, node.level, node.module)
                    hit = add(resolve_local(target, local_by_name))
                    for alias in node.names:
                        hit = add(resolve_local(f"{target}.{alias.name}", local_by_name)) or hit
                    if not hit:
                        unresolved_relative.append(f"{source} -> {target or '.'}")
                    continue

                module = node.module or ""
                hit = add(resolve_local(module, local_by_name))
                for alias in node.names:
                    hit = add(resolve_local(f"{module}.{alias.name}", local_by_name)) or hit
                if not hit and module:
                    external[module.split(".")[0]] += 1

    def _js_edges(self, path: Path, ctx, edges, external) -> None:
        text = path.read_text(errors="replace")
        source = _module_name(path, ctx.root)
        edges.setdefault(source, set())
        for match in JS_IMPORT.finditer(text):
            spec = match.group(1) or match.group(2) or ""
            if spec.startswith("."):
                edges[source].add(spec)
            elif spec and not spec.startswith(("http", "node:")):
                external[spec.split("/")[0]] += 1
