"""Shared analyzer contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from ..evidence import Evidence, Finding


@dataclass
class AnalysisContext:
    root: Path
    label: str
    kind: str
    meta: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    cache: Dict[str, Any] = field(default_factory=dict)

    def reveal(self) -> str:
        return self.root.name or self.label


class Analyzer:
    name = "analyzer"
    category = "general"

    def analyze(self, ctx: AnalysisContext) -> List[Finding]:  # pragma: no cover - interface
        raise NotImplementedError


def evidence_for(path: Path, root: Path, lines: str = "", excerpt: str = "") -> Evidence:
    try:
        locator = str(path.relative_to(root))
    except ValueError:
        locator = str(path)
    if lines:
        locator = f"{locator}:{lines}"
    return Evidence(source="local", locator=locator, excerpt=excerpt[:400])
