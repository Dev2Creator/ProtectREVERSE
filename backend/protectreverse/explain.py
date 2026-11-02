"""Explain Anything engine: three deterministic modes, evidence-linked.

No LLM is required and none is called. Every sentence is derived from a finding
that already carries its own evidence, status and confidence.
"""

from __future__ import annotations

from typing import List

from .evidence import Finding, Investigation


def _pick(inv: Investigation, categories: List[str]) -> List[Finding]:
    wanted = set(categories)
    return [f for f in inv.findings if f.category in wanted]


def _cite(finding: Finding) -> str:
    return f"[{finding.id} · {finding.status.value} · {finding.confidence.value}]"


def explain_simple(inv: Investigation) -> str:
    lines = [f"What this is: {inv.target}", ""]
    purpose = _pick(inv, ["overview.purpose"])
    if purpose:
        lines.append(f"In plain terms, the project says about itself: {purpose[0].claim}")
        lines.append("")
    stack = _pick(inv, ["overview.stack", "technology.fingerprint"])
    if stack:
        lines.append("What it is built with (as far as the files show):")
        for finding in stack[:5]:
            lines.append(f"* {finding.claim} {_cite(finding)}")
        lines.append("")
    size = _pick(inv, ["inventory.size", "inventory.languages"])
    for finding in size[:2]:
        lines.append(f"* {finding.claim} {_cite(finding)}")
    lines.append("")
    lines.append("What this investigation cannot tell you: things that only appear when the "
                 "software actually runs, like its private servers, databases, or admin areas.")
    lines.append("")
    lines.append("Where to look first: files listed in the Evidence tab, starting with the README "
                 "and the largest source files.")
    return "\n".join(lines)


def explain_developer(inv: Investigation) -> str:
    lines = [f"Developer view — {inv.target}", ""]
    for category, label in [
        ("architecture.entry_points", "Entry points"),
        ("architecture.imports", "Module relationships"),
        ("architecture.external", "External packages"),
        ("api.routes", "HTTP surface"),
        ("dependencies.declared", "Dependencies"),
        ("quality.tests", "Tests"),
        ("quality.ci", "CI"),
    ]:
        hits = _pick(inv, [category])
        if not hits:
            continue
        lines.append(f"{label}:")
        for finding in hits[:2]:
            lines.append(f"* {finding.claim} {_cite(finding)}")
            for ev in finding.evidence[:2]:
                lines.append(f"  evidence: {ev.source} {ev.locator}")
        lines.append("")
    lines.append("Practical next steps that follow from the evidence above:")
    lines.append("* Read the entry point first, then follow the import edges that have the highest fan-in.")
    lines.append("* Confirm behaviour by running the project yourself; this report never executes code.")
    return "\n".join(lines)


def explain_architect(inv: Investigation) -> str:
    lines = [f"Architect view — {inv.target}", ""]
    lines.append("System boundaries observed from files:")
    for finding in _pick(inv, ["overview.stack", "inventory.size"])[:2]:
        lines.append(f"* {finding.claim} {_cite(finding)}")
    lines.append("")
    lines.append("Component relationships:")
    for finding in _pick(inv, ["architecture.imports"])[:1]:
        lines.append(f"* {finding.claim} {_cite(finding)}")
    lines.append("")
    lines.append("External integration points:")
    for finding in _pick(inv, ["architecture.external", "api.routes"])[:2]:
        lines.append(f"* {finding.claim} {_cite(finding)}")
    lines.append("")
    lines.append("Coupling and maintenance signals:")
    for finding in _pick(inv, ["quality.module_size", "quality.tests", "quality.ci", "dependencies.lockfile"]):
        lines.append(f"* {finding.claim} {_cite(finding)}")
    lines.append("")
    unknowns = [f for f in inv.findings if f.status.value in {"UNKNOWN", "NOT_CHECKED"}]
    lines.append("Unknowns and assumptions that must be closed before architectural decisions:")
    for finding in unknowns[:5]:
        lines.append(f"* {finding.claim} {_cite(finding)}")
    return "\n".join(lines)


MODES = {
    "simple": explain_simple,
    "developer": explain_developer,
    "architect": explain_architect,
}


def explain(inv: Investigation, mode: str = "simple") -> str:
    try:
        return MODES[mode](inv)
    except KeyError:
        raise ValueError(f"unknown mode {mode!r}; choose from {', '.join(MODES)}")
