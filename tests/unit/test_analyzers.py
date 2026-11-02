"""Unit tests for analyzers against the bundled fixture project."""

from __future__ import annotations

from pathlib import Path

from protectreverse.analyzers.base import AnalysisContext
from protectreverse.analyzers.imports import ImportAnalyzer
from protectreverse.analyzers.inventory import InventoryAnalyzer
from protectreverse.analyzers.manifests import ManifestAnalyzer
from protectreverse.analyzers.routes import RoutesAnalyzer

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "python_app"


def context() -> AnalysisContext:
    ctx = AnalysisContext(root=FIXTURE, label=str(FIXTURE), kind="directory")
    InventoryAnalyzer().analyze(ctx)  # fills ctx.cache["files"]
    return ctx


def test_inventory_detects_python_and_yaml():
    ctx = context()
    languages = ctx.cache["languages"]
    assert languages["Python"] >= 3
    assert languages["YAML"] >= 1


def test_manifest_parsing_reports_declared_dependencies():
    ctx = context()
    findings = ManifestAnalyzer().analyze(ctx)
    declared = next(f for f in findings if f.category == "dependencies.declared")
    assert "requirements.txt" in declared.details["manifests"]
    assert declared.details["declared"]["requirements.txt"]["flask"] == "==3.0.3"


def test_manifest_without_lockfile_is_inferred_not_observed():
    ctx = context()
    findings = ManifestAnalyzer().analyze(ctx)
    lockfile = next(f for f in findings if f.category == "dependencies.lockfile")
    assert lockfile.status.value == "INFERRED"


def test_import_graph_links_local_module():
    ctx = context()
    findings = ImportAnalyzer().analyze(ctx)
    graph = next(f for f in findings if f.category == "architecture.imports")
    edges = graph.details["edges"]
    assert any("util" in target for targets in edges.values() for target in targets)


def test_routes_are_extracted_with_methods():
    ctx = context()
    findings = RoutesAnalyzer().analyze(ctx)
    routes = next(f for f in findings if f.category == "api.routes")
    paths = {(e["method"], e["path"]) for e in routes.details["endpoints"]}
    assert ("GET", "/") in paths
    assert ("POST", "/items") in paths


def test_route_evidence_has_real_line_numbers():
    ctx = context()
    findings = RoutesAnalyzer().analyze(ctx)
    routes = next(f for f in findings if f.category == "api.routes")
    assert all(e["line"] > 0 for e in routes.details["endpoints"])
