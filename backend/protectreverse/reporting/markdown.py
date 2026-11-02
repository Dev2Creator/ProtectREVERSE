"""Markdown report renderer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from .. import __version__
from ..evidence import Finding, Investigation

STATUS_MARK = {
    "OBSERVED": "observed",
    "INFERRED": "inferred",
    "UNKNOWN": "unknown",
    "NOT_CHECKED": "not checked",
    "CONTRADICTED": "contradicted",
}

METHOD = {
    "directory": "local directory import (read-only)",
    "archive": "ZIP import with bounded, traversal-safe extraction",
    "repository": "shallow HTTPS clone, revision pinned",
}


def render_markdown(inv: Investigation) -> str:
    counts = inv.to_dict()["counts"]["by_status"]
    lines: List[str] = []
    add = lines.append

    add(f"# Investigation report — {inv.target}")
    add("")
    add(f"* Tool: ProtectREVERSE {__version__}")
    add(f"* Investigation: `{inv.id}`")
    add(f"* Generated: {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}")
    add(f"* Target kind: {inv.target_kind} ({METHOD.get(inv.target_kind, 'unknown')})")
    if inv.meta.get("revision"):
        add(f"* Revision: `{inv.meta['revision'][:12]}`")
    add("")

    add("## Scope and method")
    add("")
    add("This report is generated from supplied material only. Nothing was executed, "
        "no authenticated area was accessed, and no forms were submitted.")
    add("")
    add("Status vocabulary: **OBSERVED** (directly present), **INFERRED** (supported but not proven), "
        "**UNKNOWN** (insufficient evidence), **NOT_CHECKED** (out of scope), "
        "**CONTRADICTED** (sources disagree). Confidence is not a guarantee of truth.")
    add("")

    add("## Evidence summary")
    add("")
    for status, mark in STATUS_MARK.items():
        add(f"* {mark}: {counts.get(status, 0)}")
    add("")

    if inv.warnings:
        add("## Warnings")
        add("")
        for warning in inv.warnings:
            add(f"* {warning}")
        add("")

    add("## Findings")
    add("")
    for finding in inv.findings:
        add(_render_finding(finding))
        add("")

    add("## Sources")
    add("")
    for source in inv.sources:
        add(f"* `{source.id}` — {source.kind}: {source.label} (collected {source.collected_at})")
        for limitation in source.limitations:
            add(f"  * limitation: {limitation}")
    add("")

    add("## Limitations of this report")
    add("")
    add("* Static observations do not prove runtime behaviour.")
    add("* Absence of a finding is not evidence of absence.")
    add("* Secret-shaped strings are redacted; their presence is not confirmation of a live credential.")
    add("* Reports are not legal, security or compliance advice.")
    add("")
    add("---")
    add("")
    add("ProtectREVERSE is provided AS IS / AS AVAILABLE. See LICENSE-EULA.md.")
    return "\n".join(lines)


def _render_finding(finding: Finding) -> str:
    header = (f"### {finding.id} — {finding.category}\n\n"
              f"**{finding.claim}**\n\n"
              f"Status: `{finding.status.value}` · Confidence: `{finding.confidence.value}`\n")
    body = []
    if finding.evidence:
        body.append("Evidence:")
        for ev in finding.evidence:
            excerpt = f" — “{ev.excerpt}”" if ev.excerpt else ""
            body.append(f"* `{ev.source}` {ev.locator} (collected {ev.collected_at}){excerpt}")
        body.append("")
    if finding.limitations:
        body.append("Limitations:")
        for limitation in finding.limitations:
            body.append(f"* {limitation}")
        body.append("")
    return header + "\n" + "\n".join(body)
