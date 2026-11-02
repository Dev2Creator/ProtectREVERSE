"""Visual analysis pipeline: markup and stylesheets in, Visual IR out.

Offline by design. The only files read are the ones the caller points at, and a
stylesheet reference is resolved inside the site root or reported as unfetched.
No network access happens here; the browser collector is a separate milestone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import codegen
from .assets import discover_assets, is_external
from .components import build_components
from .css import apply_variables, breakpoints, derive_tokens, parse_stylesheet
from .dom import parse_html
from .ir import PageIR, VisualIR


@dataclass
class VisualAnalysis:
    ir: VisualIR
    html: str
    css: str


def analyze_markup(
    markup: str,
    stylesheets: Optional[Dict[str, str]] = None,
    *,
    url: str = "about:local",
    owned: bool = True,
) -> VisualIR:
    parsed = parse_html(markup)

    rules = []
    for text in (stylesheets or {}).values():
        rules.extend(parse_stylesheet(text))
    for block in parsed.style_blocks:
        rules.extend(parse_stylesheet(block))

    variables = apply_variables(rules)
    tokens = derive_tokens(rules, variables)
    found_breakpoints = breakpoints(rules)
    assets = discover_assets(parsed.root, rules, owned=owned)
    components = build_components(parsed.root)

    warnings: List[str] = []
    if not parsed.title:
        warnings.append("page declares no <title>")
    if not parsed.root.find("h1"):
        warnings.append("page declares no <h1> heading")
    if not rules:
        warnings.append("no stylesheets found; tokens and breakpoints are empty")

    page = PageIR(
        url=url,
        title=parsed.title,
        root=parsed.root,
        node_count=parsed.node_count,
        landmarks=parsed.landmarks,
        interactions=parsed.interactions,
        stylesheets=sorted((stylesheets or {}).keys()),
    )

    ir = VisualIR(
        pages=[page],
        rules=rules,
        tokens=tokens,
        assets=assets,
        components=components,
        breakpoints=found_breakpoints,
        warnings=warnings,
    )
    return ir.validate()


def analyze_local_site(root: Path, entry: str = "index.html") -> VisualIR:
    base = Path(root).resolve()
    target = (base / entry).resolve()
    if not target.is_file():
        raise ValueError(f"entry file not found: {target}")
    if not target.is_relative_to(base):
        raise ValueError("entry file escapes the site root")

    markup = target.read_text(encoding="utf-8", errors="replace")
    preliminary = parse_html(markup)

    sheets: Dict[str, str] = {}
    warnings: List[str] = []
    for node in preliminary.root.find("link"):
        if "stylesheet" not in node.attrs.get("rel", "").lower():
            continue
        href = node.attrs.get("href", "").strip()
        if not href:
            continue
        if is_external(href):
            warnings.append(f"external stylesheet not fetched: {href}")
            continue
        candidate = (base / href.lstrip("/")).resolve()
        if candidate.is_file() and candidate.is_relative_to(base):
            sheets[href] = candidate.read_text(encoding="utf-8", errors="replace")
        else:
            warnings.append(f"stylesheet not found inside the site root: {href}")

    ir = analyze_markup(markup, sheets, url=target.name, owned=True)
    ir.warnings.extend(warnings)
    return ir.validate()


def analyze_and_emit(markup: str, stylesheets: Optional[Dict[str, str]] = None, **kwargs) -> VisualAnalysis:
    ir = analyze_markup(markup, stylesheets, **kwargs)
    return VisualAnalysis(ir=ir, html=codegen.to_html(ir), css=codegen.to_css(ir))


def write_outputs(ir: VisualIR, out_dir: Path) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: Dict[str, Path] = {}

    payloads = {
        "ir": ("visual-ir.json", ir.to_dict()),
        "tokens": ("design-tokens.json", {
            "tokens": [t.to_dict() for t in ir.tokens],
            "breakpoints": ir.breakpoints,
        }),
        "components": ("components.json", [c.to_dict() for c in ir.components]),
        "assets": ("assets.json", [a.to_dict() for a in ir.assets]),
    }
    for key, (name, payload) in payloads.items():
        path = out / name
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        files[key] = path

    html_path = out / "reconstruction.html"
    html_path.write_text(codegen.to_html(ir), encoding="utf-8")
    files["html"] = html_path

    css_path = out / "reconstruction.css"
    css_path.write_text(codegen.to_css(ir), encoding="utf-8")
    files["css"] = css_path

    design_path = out / "DESIGN_SYSTEM.md"
    design_path.write_text(render_design_system(ir), encoding="utf-8")
    files["design"] = design_path
    return files


def render_design_system(ir: VisualIR) -> str:
    lines: List[str] = ["# Design system reconstruction", ""]
    lines.append(
        "Every value below is derived from collected markup and stylesheets. "
        "Component names are inferred; node selectors are observed."
    )
    lines.append("")

    for page in ir.pages:
        lines.append(f"## Page: {page.title or page.url}")
        lines.append("")
        lines.append(f"- Source: `{page.url}`")
        lines.append(f"- Nodes: {page.node_count}")
        lines.append(f"- Landmarks: {', '.join(page.landmarks) or 'none declared'}")
        lines.append(f"- Interactions: {', '.join(f'{k} x{v}' for k, v in sorted(page.interactions.items())) or 'none declared'}")
        lines.append("")

    lines.append("## Design tokens")
    lines.append("")
    if ir.tokens:
        lines.append("| Name | Kind | Value | Uses |")
        lines.append("| --- | --- | --- | --- |")
        for token in ir.tokens:
            lines.append(f"| `{token.name}` | {token.kind} | `{token.value}` | {token.usage} |")
    else:
        lines.append("No tokens were derived; no stylesheet provided a value.")
    lines.append("")

    lines.append("## Responsive breakpoints")
    lines.append("")
    if ir.breakpoints:
        for entry in ir.breakpoints:
            lines.append(f"- {entry['kind']}-width: {entry['value']}{entry['unit']} ({entry['rules']} rule(s))")
    else:
        lines.append("No media queries were found.")
    lines.append("")

    lines.append("## Components (inferred)")
    lines.append("")
    if ir.components:
        lines.append("| Name | Count | Example selector |")
        lines.append("| --- | --- | --- |")
        for component in ir.components[:20]:
            selector = component.selectors[0] if component.selectors else "-"
            lines.append(f"| `{component.name}` | {component.count} | `{selector}` |")
    else:
        lines.append("No repeated subtree reached the clustering threshold.")
    lines.append("")

    lines.append("## Assets")
    lines.append("")
    if ir.assets:
        lines.append("| URL | Kind | MIME | Licence |")
        lines.append("| --- | --- | --- | --- |")
        for asset in ir.assets[:40]:
            lines.append(f"| `{asset.url}` | {asset.kind} | {asset.mime or 'unknown'} | {asset.licence.value} |")
    else:
        lines.append("No assets referenced.")
    lines.append("")

    if ir.warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in ir.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("## Limits")
    lines.append("")
    lines.append(
        "This reconstruction comes from markup and authored CSS only. Rendered layout, "
        "computed styles, hover and focus states, and responsive behaviour under a real "
        "viewport require the browser collector. Nothing here proves how the site behaves at runtime."
    )
    return "\n".join(lines) + "\n"
