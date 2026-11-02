"""Component reconstruction from repeated DOM structure.

A component here is a *hypothesis*: a subtree signature that repeats across the
page. Naming and prop inference are inferred, never observed, and every claim
cites the node ids it came from.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .ir import ComponentIR, NodeIR, Provenance

SKIP_TAGS = {"#document", "html", "head", "body", "script", "style", "link", "meta", "title"}
STRUCTURAL_DEPTH = 2


def signature(node: NodeIR, depth: int = 0) -> str:
    """Structural fingerprint: tag, up to two classes, child tags down to a depth limit."""
    classes = sorted(node.attrs.get("class", "").split())[:2]
    head = node.tag if not classes else f"{node.tag}.{'.'.join(classes)}"
    if depth >= STRUCTURAL_DEPTH:
        return head
    children = [c for c in node.children if c.tag not in SKIP_TAGS]
    if not children:
        return head
    inner = ",".join(signature(child, depth + 1) for child in children)
    return f"{head}[{inner}]"


def _component_name(node: NodeIR, used: set) -> str:
    classes = node.attrs.get("class", "").split()
    if classes:
        base = classes[0]
    elif node.attrs.get("id"):
        base = node.attrs["id"]
    else:
        base = f"{node.tag}-group"
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}-{index}"
        index += 1
    used.add(candidate)
    return candidate


def build_components(root: NodeIR, min_count: int = 2, limit: int = 40) -> List[ComponentIR]:
    buckets: Dict[str, List[NodeIR]] = defaultdict(list)

    def visit(node: NodeIR, depth: int) -> None:
        if node.tag in SKIP_TAGS:
            for child in node.children:
                visit(child, depth)
            return
        if depth > 0:
            buckets[signature(node)].append(node)
        for child in node.children:
            visit(child, depth + 1)

    visit(root, 0)

    candidates = [
        (sig, nodes) for sig, nodes in buckets.items()
        if len(nodes) >= min_count and all(n.tag not in SKIP_TAGS for n in nodes)
    ]
    candidates.sort(key=lambda item: (-len(item[1]), item[0]))

    used_names: set = set()
    components: List[ComponentIR] = []
    for sig, nodes in candidates[:limit]:
        first = nodes[0]
        components.append(ComponentIR(
            name=_component_name(first, used_names),
            signature=sig,
            count=len(nodes),
            selectors=[n.selector for n in nodes[:3]],
            node_ids=[n.node_id for n in nodes[:5]],
            confidence=Provenance.INFERRED,
        ))
    return components
