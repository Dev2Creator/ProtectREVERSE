"""End-to-end pipeline: analyse the fixture, export, explain, plan, delete."""

from __future__ import annotations

import json
from pathlib import Path

from protectreverse.agentmd import generate_agent_md
from protectreverse.analyzers.local import analyze_target
from protectreverse.cli import main
from protectreverse.explain import explain
from protectreverse.intake import open_local
from protectreverse.planner import build_plan
from protectreverse.workspace import delete, export_reports, load, save

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "python_app"


def test_full_analysis_produces_labelled_findings(tmp_path):
    target = open_local(FIXTURE)
    inv = analyze_target(target)
    statuses = {f.status.value for f in inv.findings}

    assert {"OBSERVED", "INFERRED", "NOT_CHECKED"} <= statuses
    assert all(f.evidence for f in inv.findings if f.status.value == "OBSERVED"
               and f.category not in {"overview.stack"})
    assert any(f.category == "scope.not_checked" for f in inv.findings)


def test_exports_never_contain_secret_values(tmp_path):
    target = open_local(FIXTURE)
    inv = analyze_target(target)
    written = export_reports(inv, ["md", "html", "json"], tmp_path)

    blob = "".join(path.read_text() for path in written.values())
    assert "sk_test_1234567890abcdefghijklmnop" not in blob
    assert "hunter2" not in blob
    assert "secret-shaped" in blob.lower()


def test_exports_are_valid_json_and_html(tmp_path):
    target = open_local(FIXTURE)
    inv = analyze_target(target)
    written = export_reports(inv, ["json", "html"], tmp_path)

    data = json.loads(written["json"].read_text())
    assert data["counts"]["findings"] == len(inv.findings)
    assert data["tool"]["name"] == "ProtectREVERSE"

    html = written["html"].read_text()
    assert "<title>" in html and "ProtectREVERSE" in html
    assert "findings" in html  # the data payload is embedded


def test_three_explanation_modes_are_evidence_linked():
    target = open_local(FIXTURE)
    inv = analyze_target(target)
    for mode in ("simple", "developer", "architect"):
        text = explain(inv, mode)
        assert text.strip()
        assert "F0" in text  # cites at least one finding id


def test_planner_tasks_reference_real_findings():
    target = open_local(FIXTURE)
    inv = analyze_target(target)
    plan = build_plan(inv)
    known = {f.id for f in inv.findings}

    assert plan["tasks"]
    for task in plan["tasks"]:
        assert task["evidence"] == [] or set(task["evidence"]) <= known
        assert task["acceptance_criteria"]


def test_agentmd_modes_keep_registers_apart():
    target = open_local(FIXTURE)
    inv = analyze_target(target)
    for mode in ("understand", "build", "modernize", "documentation"):
        text = generate_agent_md(inv, mode)
        assert "Observed facts" in text
        assert "PROPOSAL" in text
        assert "Requirements to confirm" in text


def test_workspace_roundtrip_and_delete():
    target = open_local(FIXTURE)
    inv = analyze_target(target)
    save(inv)
    reloaded = load(inv.id)
    assert reloaded.target == inv.target
    assert len(reloaded.findings) == len(inv.findings)
    assert delete(inv.id) is True
    assert delete(inv.id) is False


def test_cli_scan_writes_requested_outputs(tmp_path, capsys):
    code = main([
        "scan", str(FIXTURE),
        "--out", str(tmp_path),
        "--plan",
        "--agentmd", "build",
        "--json-summary",
    ])
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["counts"]["findings"] > 0
    assert Path(summary["outputs"]["md"]).exists()
    assert Path(summary["outputs"]["agentmd"]).exists()
    assert summary["outputs"]["plan"].endswith("-plan.md")


def test_cli_refuses_unsafe_target(capsys):
    code = main(["scan", "http://127.0.0.1:8000/"])
    assert code == 2
    assert "refused" in capsys.readouterr().out
