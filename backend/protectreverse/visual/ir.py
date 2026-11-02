"""Intermediate representation for visual, DOM, CSS and asset evidence.

Every artefact carries provenance: what the browser or markup actually showed
(observed), what was reconstructed from it (inferred), and what could not be
determined (unknown). The IR is the single contract between collection,
analysis, comparison and code generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional

IR_VERSION = "visual-ir/1"


class Provenance(str, Enum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class LicenceStatus(str, Enum):
    OWNED = "owned"
    LICENSED = "licensed"
    UNKNOWN = "unknown"
    RESTRICTED = "restricted"


class IRValidationError(ValueError):
    """Raised when an IR violates its own invariants."""


@dataclass
class NodeIR:
    node_id: str
    tag: str
    attrs: Dict[str, str] = field(default_factory=dict)
    text: str = ""
    selector: str = ""
    role: str = ""
    children: List["NodeIR"] = field(default_factory=list)
    provenance: Provenance = Provenance.OBSERVED

    def walk(self) -> Iterator["NodeIR"]:
        yield self
        for child in self.children:
            yield from child.walk()

    def find(self, tag: str) -> List["NodeIR"]:
        return [n for n in self.walk() if n.tag == tag]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "tag": self.tag,
            "attrs": dict(self.attrs),
            "text": self.text,
            "selector": self.selector,
            "role": self.role,
            "provenance": self.provenance.value,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class RuleIR:
    selector: str
    declarations: Dict[str, str] = field(default_factory=dict)
    media: Optional[str] = None
    specificity: tuple = (0, 0, 0)
    origin: str = "authored"
    provenance: Provenance = Provenance.OBSERVED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selector": self.selector,
            "declarations": dict(self.declarations),
            "media": self.media,
            "specificity": list(self.specificity),
            "origin": self.origin,
            "provenance": self.provenance.value,
        }


@dataclass
class TokenIR:
    kind: str
    name: str
    value: str
    usage: int = 1
    provenance: Provenance = Provenance.OBSERVED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "value": self.value,
            "usage": self.usage,
            "provenance": self.provenance.value,
        }


@dataclass
class AssetIR:
    url: str
    kind: str
    mime: str = ""
    byte_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    licence: LicenceStatus = LicenceStatus.UNKNOWN
    used_in: List[str] = field(default_factory=list)
    provenance: Provenance = Provenance.OBSERVED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "kind": self.kind,
            "mime": self.mime,
            "byte_size": self.byte_size,
            "width": self.width,
            "height": self.height,
            "licence": self.licence.value,
            "used_in": list(self.used_in),
            "provenance": self.provenance.value,
        }


@dataclass
class ComponentIR:
    name: str
    signature: str
    count: int
    selectors: List[str] = field(default_factory=list)
    node_ids: List[str] = field(default_factory=list)
    confidence: Provenance = Provenance.INFERRED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "signature": self.signature,
            "count": self.count,
            "selectors": list(self.selectors),
            "node_ids": list(self.node_ids),
            "confidence": self.confidence.value,
        }


@dataclass
class PageIR:
    url: str
    title: str
    root: NodeIR
    node_count: int = 0
    landmarks: List[str] = field(default_factory=list)
    interactions: Dict[str, int] = field(default_factory=dict)
    stylesheets: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "node_count": self.node_count,
            "landmarks": list(self.landmarks),
            "interactions": dict(self.interactions),
            "stylesheets": list(self.stylesheets),
            "root": self.root.to_dict(),
        }


@dataclass
class VisualIR:
    pages: List[PageIR] = field(default_factory=list)
    rules: List[RuleIR] = field(default_factory=list)
    tokens: List[TokenIR] = field(default_factory=list)
    assets: List[AssetIR] = field(default_factory=list)
    components: List[ComponentIR] = field(default_factory=list)
    breakpoints: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    version: str = IR_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "pages": [p.to_dict() for p in self.pages],
            "rules": [r.to_dict() for r in self.rules],
            "tokens": [t.to_dict() for t in self.tokens],
            "assets": [a.to_dict() for a in self.assets],
            "components": [c.to_dict() for c in self.components],
            "breakpoints": [dict(b) for b in self.breakpoints],
            "warnings": list(self.warnings),
        }

    @property
    def node_total(self) -> int:
        return sum(p.node_count for p in self.pages)

    def tokens_of(self, kind: str) -> List[TokenIR]:
        return [t for t in self.tokens if t.kind == kind]

    def validate(self) -> "VisualIR":
        if not self.pages:
            raise IRValidationError("IR has no pages")
        seen_nodes: set = set()
        for page in self.pages:
            if page.root.tag != "#document":
                raise IRValidationError(f"page {page.url!r} root must be #document")
            for node in page.root.walk():
                if node.node_id in seen_nodes:
                    raise IRValidationError(f"duplicate node id {node.node_id!r}")
                seen_nodes.add(node.node_id)
                if node.tag != "#document" and not node.selector:
                    raise IRValidationError(f"node {node.node_id!r} has no selector")
        for comp in self.components:
            missing = [n for n in comp.node_ids if n not in seen_nodes]
            if missing:
                raise IRValidationError(
                    f"component {comp.name!r} cites unknown nodes {missing[:3]}"
                )
            if comp.count < 1:
                raise IRValidationError(f"component {comp.name!r} has count < 1")
        for asset in self.assets:
            if not asset.url:
                raise IRValidationError("asset without url")
        for token in self.tokens:
            if not token.value:
                raise IRValidationError(f"token {token.name!r} has no value")
        for bp in self.breakpoints:
            if "kind" not in bp or "value" not in bp:
                raise IRValidationError(f"malformed breakpoint {bp!r}")
        return self
