"""Implementation planner: evidence-derived, editable, exportable tasks."""

from __future__ import annotations

import json
from typing import Dict, List

from .evidence import Investigation

RULES = [
    {
        "match": "security.secret_like_strings",
        "title": "Review and remove secret-shaped strings",
        "priority": "critical",
        "complexity": "S",
        "acceptance": "No secret-shaped string remains in tracked files; any real credential is rotated out-of-band",
        "tests": "Add a pre-commit secret scan that fails the build",
        "depends_on": [],
    },
    {
        "match": "quality.tests",
        "title": "Add automated tests around the entry point",
        "priority": "high",
        "complexity": "M",
        "acceptance": "The main entry point and one core module are covered by tests that run offline",
        "tests": "Test suite runs in CI with a failing exit code on regression",
        "depends_on": [],
    },
    {
        "match": "quality.ci",
        "title": "Establish a CI pipeline",
        "priority": "high",
        "complexity": "S",
        "acceptance": "Every push runs lint and tests and reports status on the repository",
        "tests": "A deliberately failing commit is blocked",
        "depends_on": ["quality.tests"],
    },
    {
        "match": "dependencies.lockfile",
        "title": "Pin dependency versions with a lockfile",
        "priority": "medium",
        "complexity": "S",
        "acceptance": "A lockfile is committed and reproducible installs succeed from scratch",
        "tests": "Clean-environment install resolves identical versions twice",
        "depends_on": [],
    },
    {
        "match": "quality.module_size",
        "title": "Split modules that are hard to review",
        "priority": "medium",
        "complexity": "M",
        "acceptance": "No module exceeds the agreed size budget; behaviour unchanged before and after",
        "tests": "Existing tests pass unchanged after the split",
        "depends_on": ["quality.tests"],
    },
    {
        "match": "quality.documentation",
        "title": "Document purpose, setup and architecture",
        "priority": "medium",
        "complexity": "S",
        "acceptance": "A new contributor can install, run and navigate the project from the README alone",
        "tests": "A fresh-environment walkthrough succeeds without verbal help",
        "depends_on": [],
    },
    {
        "match": "api.routes",
        "title": "Document the detected HTTP surface",
        "priority": "medium",
        "complexity": "M",
        "acceptance": "Documented endpoints match the detected routes, including methods and paths",
        "tests": "Contract tests cover each documented endpoint",
        "depends_on": [],
    },
    {
        "match": "architecture.entry_points",
        "title": "Trace and document the execution path from the entry point",
        "priority": "high",
        "complexity": "M",
        "acceptance": "Execution flow from entry point to core logic is written down and verified by reading the code",
        "tests": "A smoke test starts the application and exercises the primary path",
        "depends_on": [],
    },
]


def build_plan(inv: Investigation) -> Dict[str, object]:
    categories = {f.category: f for f in inv.findings}
    tasks: List[Dict[str, object]] = []
    for index, rule in enumerate(RULES, start=1):
        finding = categories.get(rule["match"])
        if not finding:
            continue
        tasks.append({
            "task_id": f"T{index:02d}",
            "title": rule["title"],
            "description": f"Triggered by finding {finding.id}: {finding.claim}",
            "priority": rule["priority"],
            "complexity": rule["complexity"],
            "depends_on": rule["depends_on"],
            "acceptance_criteria": rule["acceptance"],
            "test_requirements": rule["tests"],
            "evidence": [finding.id],
            "status": "pending",
        })

    tasks.append({
        "task_id": f"T{len(tasks) + 1:02d}",
        "title": "Close the recorded unknowns before relying on this report",
        "description": "The investigation lists what static analysis could not establish. "
                       "Resolve those items by reading code or by asking the system's owners.",
        "priority": "high",
        "complexity": "S",
        "depends_on": [],
        "acceptance_criteria": "Each UNKNOWN and NOT_CHECKED finding is either resolved with evidence or explicitly accepted as a risk",
        "test_requirements": "Written decision record per open question",
        "evidence": [f.id for f in inv.findings if f.status.value in {"UNKNOWN", "NOT_CHECKED"}],
        "status": "pending",
    })

    return {
        "investigation": inv.id,
        "target": inv.target,
        "generated_from": "observed findings only",
        "tasks": tasks,
    }


def render_plan_markdown(plan: Dict[str, object]) -> str:
    lines = [f"# Implementation plan — {plan['target']}", ""]
    lines.append(f"Investigation: `{plan['investigation']}` · derived from {plan['generated_from']}")
    lines.append("")
    lines.append("Tasks are ordered by priority. Every task cites the finding that triggered it; "
                 "nothing here is invented beyond the recorded evidence.")
    lines.append("")
    for task in plan["tasks"]:
        lines.append(f"## {task['task_id']} — {task['title']}")
        lines.append("")
        lines.append(f"* Priority: {task['priority']} · Complexity: {task['complexity']} · Status: {task['status']}")
        lines.append(f"* Depends on: {', '.join(task['depends_on']) or 'none'}")
        lines.append(f"* Evidence: {', '.join(task['evidence']) or 'none'}")
        lines.append("")
        lines.append(f"**Why:** {task['description']}")
        lines.append("")
        lines.append(f"**Done when:** {task['acceptance_criteria']}")
        lines.append("")
        lines.append(f"**Testing:** {task['test_requirements']}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("This plan is derived from static observations and may be incomplete. "
                 "Edit it before treating it as a commitment.")
    return "\n".join(lines)


def render_plan_json(plan: Dict[str, object]) -> str:
    return json.dumps(plan, indent=2, ensure_ascii=False)
