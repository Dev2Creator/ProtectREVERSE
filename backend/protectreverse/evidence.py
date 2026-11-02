"""Evidence model.

A finding is only worth recording if it carries where it came from, when it was
collected, how confident we are and what it does *not* prove.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class Status(str, Enum):
    OBSERVED = "OBSERVED"          # directly present in supplied or public material
    INFERRED = "INFERRED"          # supported conclusion, not directly proven
    UNKNOWN = "UNKNOWN"            # insufficient evidence
    NOT_CHECKED = "NOT_CHECKED"    # outside scope / unsupported
    CONTRADICTED = "CONTRADICTED"  # credible sources disagree


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Evidence:
    source: str                 # "local:src/app.py", "git:HEAD", "https://example.com"
    locator: str                # file path, URL fragment, line range
    excerpt: str = ""           # redacted, size-capped
    collected_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Finding:
    category: str
    claim: str
    status: Status
    confidence: Confidence
    evidence: List[Evidence] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["confidence"] = self.confidence.value
        return data


@dataclass
class Source:
    id: str
    kind: str
    label: str
    collected_at: str = field(default_factory=now_iso)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Investigation:
    """In-memory investigation with a stable, deterministic serialisation."""

    def __init__(self, target: str, target_kind: str, meta: Optional[Dict[str, Any]] = None):
        digest = hashlib.sha256(f"{target}|{now_iso()}".encode()).hexdigest()[:10]
        self.id = f"inv-{digest}"
        self.target = target
        self.target_kind = target_kind
        self.created_at = now_iso()
        self.meta: Dict[str, Any] = meta or {}
        self.findings: List[Finding] = []
        self.sources: List[Source] = []
        self.notes: List[Dict[str, str]] = []
        self.warnings: List[str] = []
        self._finding_seq = 0
        self._source_seq = 0

    # -- collection ---------------------------------------------------------
    def add_source(self, kind: str, label: str, limitations: Optional[List[str]] = None) -> Source:
        self._source_seq += 1
        source = Source(id=f"S{self._source_seq}", kind=kind, label=label,
                        limitations=limitations or [])
        self.sources.append(source)
        return source

    def add_finding(
        self,
        category: str,
        claim: str,
        status: Status,
        confidence: Confidence,
        evidence: Optional[List[Evidence]] = None,
        limitations: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Finding:
        self._finding_seq += 1
        finding = Finding(
            id=f"F{self._finding_seq:03d}",
            category=category,
            claim=claim,
            status=status,
            confidence=confidence,
            evidence=evidence or [],
            limitations=limitations or [],
            details=details or {},
        )
        self.findings.append(finding)
        return finding

    # -- views --------------------------------------------------------------
    def by_status(self) -> Dict[str, List[Finding]]:
        grouped: Dict[str, List[Finding]] = {status.value: [] for status in Status}
        for finding in self.findings:
            grouped[finding.status.value].append(finding)
        return grouped

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "target_kind": self.target_kind,
            "created_at": self.created_at,
            "meta": self.meta,
            "sources": [s.to_dict() for s in self.sources],
            "findings": [f.to_dict() for f in self.findings],
            "notes": self.notes,
            "warnings": self.warnings,
            "counts": {
                "findings": len(self.findings),
                "by_status": {k: len(v) for k, v in self.by_status().items()},
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Investigation":
        inv = cls(data["target"], data["target_kind"], data.get("meta"))
        inv.id = data.get("id", inv.id)
        inv.created_at = data.get("created_at", inv.created_at)
        for source in data.get("sources", []):
            inv._source_seq += 1
            inv.sources.append(Source(**{**source, "id": source.get("id", f"S{inv._source_seq}")}))
        for raw in data.get("findings", []):
            finding = Finding(
                category=raw["category"],
                claim=raw["claim"],
                status=Status(raw["status"]),
                confidence=Confidence(raw["confidence"]),
                evidence=[Evidence(**e) for e in raw.get("evidence", [])],
                limitations=raw.get("limitations", []),
                details=raw.get("details", {}),
                id=raw.get("id", ""),
            )
            inv.findings.append(finding)
            inv._finding_seq += 1
        inv.notes = data.get("notes", [])
        inv.warnings = data.get("warnings", [])
        return inv
