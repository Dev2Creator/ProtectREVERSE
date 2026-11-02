"""DOM reconstruction from markup.

Parses HTML into NodeIR with stable selectors, roles and interaction counts.
This is the offline path: it describes what the markup declares. Rendered
layout, computed styles and responsive behaviour require the browser collector
(see VISUAL_ENGINE_PLAN.md, milestone V1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List

from .ir import NodeIR

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

TEXT_EXCLUDED = {"script", "noscript"}

ROLE_BY_TAG: Dict[str, str] = {
    "header": "banner",
    "nav": "navigation",
    "main": "main",
    "footer": "contentinfo",
    "aside": "complementary",
    "form": "form",
    "section": "region",
    "article": "article",
    "figure": "figure",
    "dialog": "dialog",
    "details": "group",
    "table": "table",
    "ul": "list",
    "ol": "list",
    "li": "listitem",
    "a": "link",
    "button": "button",
    "img": "img",
    "input": "textbox",
    "select": "combobox",
    "textarea": "textbox",
}

for _level in range(1, 7):
    ROLE_BY_TAG[f"h{_level}"] = "heading"

INTERACTION_TAGS = ("a", "button", "form", "input", "select", "textarea", "details")


@dataclass
class ParsedPage:
    title: str
    root: NodeIR
    style_blocks: List[str] = field(default_factory=list)
    node_count: int = 0
    landmarks: List[str] = field(default_factory=list)
    interactions: Dict[str, int] = field(default_factory=dict)


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = NodeIR(node_id="n0", tag="#document")
        self.stack: List[NodeIR] = [self.root]
        self.title = ""
        self.style_blocks: List[str] = []
        self._count = 0
        self._in_title = False
        self._in_style = False

    def _make(self, tag: str, attrs) -> NodeIR:
        self._count += 1
        clean = {}
        for key, value in attrs:
            clean[key.lower()] = (value or "").strip()
        node = NodeIR(node_id=f"n{self._count}", tag=tag, attrs=clean)
        self.stack[-1].children.append(node)
        return node

    def handle_starttag(self, tag, attrs):  # noqa: D102
        tag = tag.lower()
        node = self._make(tag, attrs)
        if tag in VOID_TAGS:
            return
        self.stack.append(node)
        if tag == "title":
            self._in_title = True
        elif tag == "style":
            self._in_style = True

    def handle_startendtag(self, tag, attrs):  # noqa: D102
        self._make(tag.lower(), attrs)

    def handle_endtag(self, tag):  # noqa: D102
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        elif tag == "style":
            self._in_style = False
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):  # noqa: D102
        if self._in_title:
            self.title = f"{self.title} {data}".strip()
            current = self.stack[-1]
            current.text = f"{current.text} {data}".strip() if current.text else " ".join(data.split())
            return
        if self._in_style:
            self.style_blocks.append(data)
            return
        text = " ".join(data.split())
        if not text:
            return
        current = self.stack[-1]
        if current.tag in TEXT_EXCLUDED:
            return
        current.text = f"{current.text} {text}".strip() if current.text else text


def _role_for(node: NodeIR) -> str:
    explicit = node.attrs.get("role", "").strip()
    if explicit:
        return explicit
    return ROLE_BY_TAG.get(node.tag, "")


def _assign_derived(node: NodeIR) -> None:
    counts: Dict[str, int] = {}
    for child in node.children:
        counts[child.tag] = counts.get(child.tag, 0) + 1
        index = counts[child.tag]
        if child.attrs.get("id"):
            base = f"{child.tag}#{child.attrs['id']}"
        elif child.attrs.get("class"):
            classes = ".".join(child.attrs["class"].split()[:2])
            base = f"{child.tag}.{classes}"
        elif index > 1:
            base = f"{child.tag}:nth-of-type({index})"
        else:
            base = child.tag
        if node.tag == "#document":
            child.selector = base
        else:
            child.selector = f"{node.selector} > {base}"
        child.role = _role_for(child)
        _assign_derived(child)


def parse_html(markup: str, max_nodes: int = 20000) -> ParsedPage:
    builder = _Builder()
    builder.feed(markup)
    builder.close()
    _assign_derived(builder.root)

    nodes = list(builder.root.walk())
    if len(nodes) - 1 > max_nodes:
        raise ValueError(f"markup exceeds node budget ({len(nodes) - 1} > {max_nodes})")

    landmarks = [n.role for n in nodes if n.role in {
        "banner", "navigation", "main", "contentinfo", "complementary", "region", "form", "search",
    }]
    interactions: Dict[str, int] = {}
    for node in nodes:
        if node.tag in INTERACTION_TAGS:
            interactions[node.tag] = interactions.get(node.tag, 0) + 1

    return ParsedPage(
        title=builder.title,
        root=builder.root,
        style_blocks=builder.style_blocks,
        node_count=len(nodes) - 1,
        landmarks=landmarks,
        interactions=interactions,
    )
