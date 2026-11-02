"""Regression tests for the local-module resolver (bug fixed at line 164)."""

from __future__ import annotations

from pathlib import Path

from protectreverse.analyzers.base import AnalysisContext
from protectreverse.analyzers.imports import ImportAnalyzer, resolve_local


def build(tmp_path: Path, files: dict[str, str]) -> AnalysisContext:
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    root = tmp_path
    files_list = [p for p in root.rglob("*.py")]
    ctx = AnalysisContext(root=root, label=str(root), kind="directory")
    ctx.cache["files"] = files_list
    return ctx


def graph(ctx: AnalysisContext) -> dict[str, set[str]]:
    findings = ImportAnalyzer().analyze(ctx)
    entry = next(f for f in findings if f.category == "architecture.imports")
    return {k: set(v) for k, v in entry.details.get("edges", {}).items()}


def categories(ctx: AnalysisContext) -> list[str]:
    return [f.category for f in ImportAnalyzer().analyze(ctx)]


def test_resolve_local_prefers_exact_match():
    local = {"pkg": Path("pkg/__init__.py"), "pkg.sub": Path("pkg/sub.py")}
    assert resolve_local("pkg.sub", local) == "pkg.sub"
    assert resolve_local("pkg", local) == "pkg"


def test_resolve_local_returns_none_for_strangers():
    assert resolve_local("requests", {"app": Path("app.py")}) is None
    assert resolve_local("", {"app": Path("app.py")}) is None


def test_nested_package_absolute_import(tmp_path):
    ctx = build(tmp_path, {
        "app.py": "from pkg.sub.mod import thing\n",
        "pkg/__init__.py": "",
        "pkg/sub/__init__.py": "",
        "pkg/sub/mod.py": "thing = 1\n",
    })
    assert "pkg.sub.mod" in graph(ctx).get("app", set())


def test_from_package_import_submodule(tmp_path):
    ctx = build(tmp_path, {
        "app.py": "from pkg import sub\n",
        "pkg/__init__.py": "",
        "pkg/sub/__init__.py": "value = 2\n",
    })
    assert "pkg.sub" in graph(ctx).get("app", set())


def test_relative_sibling_import(tmp_path):
    ctx = build(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/main.py": "from . import helper\n",
        "pkg/helper.py": "x = 1\n",
    })
    assert "pkg.helper" in graph(ctx).get("pkg.main", set())


def test_relative_parent_import(tmp_path):
    ctx = build(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/core.py": "y = 2\n",
        "pkg/sub/__init__.py": "",
        "pkg/sub/main.py": "from ..core import y\n",
    })
    assert "pkg.core" in graph(ctx).get("pkg.sub.main", set())


def test_missing_module_is_external_not_an_edge(tmp_path):
    ctx = build(tmp_path, {"app.py": "import definitely_missing_pkg\n"})
    findings = ImportAnalyzer().analyze(ctx)
    assert "architecture.imports" in [f.category for f in findings]
    edges = graph(ctx)
    assert "definitely_missing_pkg" not in edges.get("app", set())
    external = next(f for f in findings if f.category == "architecture.external")
    assert "definitely_missing_pkg" in external.details["external_imports"]


def test_unresolved_relative_import_is_reported(tmp_path):
    ctx = build(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "from .missing import thing\n",
    })
    assert "architecture.unresolved_imports" in categories(ctx)


def test_circular_imports_are_detected_without_recursion_error(tmp_path):
    ctx = build(tmp_path, {
        "a.py": "import b\nvalue_a = 1\n",
        "b.py": "import a\nvalue_b = 2\n",
    })
    edges = graph(ctx)
    assert "b" in edges.get("a", set())
    assert "a" in edges.get("b", set())
    assert "architecture.cycles" in categories(ctx)


def test_self_import_does_not_crash(tmp_path):
    ctx = build(tmp_path, {"loop.py": "import loop\n"})
    assert "architecture.imports" in categories(ctx)
