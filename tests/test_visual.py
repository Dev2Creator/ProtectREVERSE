"""Tests for the visual / DOM / CSS / asset engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from protectreverse.visual import (
    IRValidationError,
    LicenceStatus,
    NodeIR,
    PageIR,
    VisualIR,
    analyze_local_site,
    analyze_markup,
    parse_html,
    parse_stylesheet,
    resolve_value,
    specificity,
    write_outputs,
)
from protectreverse.visual import codegen
from protectreverse.visual.assets import discover_assets
from protectreverse.visual.components import build_components

FIXTURE = Path(__file__).parent / "fixtures" / "site"

SIMPLE_MARKUP = """
<html><head><title>Sample</title></head>
<body><header class="top"><nav><a href="/">Home</a></nav></header>
<main><h1>Title</h1><p class="lede">Text</p></main></body></html>
"""


def test_parse_html_builds_tree_and_selectors():
    parsed = parse_html(SIMPLE_MARKUP)
    assert parsed.title == "Sample"
    tags = [node.tag for node in parsed.root.walk()]
    assert "h1" in tags and "header" in tags
    heading = parsed.root.find("h1")[0]
    assert heading.selector == "html > body > main > h1"
    assert heading.text == "Title"
    assert parsed.node_count >= 8


def test_parse_html_reports_landmarks_and_interactions():
    parsed = parse_html(SIMPLE_MARKUP)
    assert "banner" in parsed.landmarks
    assert "navigation" in parsed.landmarks
    assert parsed.interactions.get("a") == 1


def test_parse_html_enforces_node_budget():
    with pytest.raises(ValueError):
        parse_html(SIMPLE_MARKUP, max_nodes=2)


def test_stylesheet_parsing_and_specificity():
    rules = parse_stylesheet(".card h3 { font-size: 18px; color: #111; } #app .x { color: #222; }")
    assert len(rules) == 2
    assert rules[0].selector == ".card h3"
    assert rules[0].declarations["font-size"] == "18px"
    assert rules[0].specificity == (0, 1, 1)
    assert rules[1].specificity == (1, 1, 0)
    assert specificity("a:hover") == (0, 1, 1)


def test_media_queries_are_nested_without_losing_rules():
    css = """
    @media (min-width: 640px) { .grid { display: grid; } }
    .base { color: #000; }
    """
    rules = parse_stylesheet(css)
    media_rules = [r for r in rules if r.media]
    assert len(media_rules) == 1
    assert media_rules[0].media == "(min-width: 640px)"
    assert any(r.selector == ".base" and r.media is None for r in rules)


def test_variable_resolution_handles_chains_and_missing_values():
    variables = {"--a": "var(--b)", "--b": "#000"}
    assert resolve_value("var(--a)", variables) == "#000"
    assert resolve_value("var(--missing)", {}) == "var(--missing)"
    assert resolve_value("var(--missing, #fff)", {}) == "#fff"


def test_ir_validation_rejects_duplicate_node_ids():
    first = NodeIR(node_id="n1", tag="div", selector="div")
    second = NodeIR(node_id="n1", tag="span", selector="span")
    ir = VisualIR(pages=[PageIR(
        url="x", title="x",
        root=NodeIR(node_id="n0", tag="#document", children=[first, second]),
    )])
    with pytest.raises(IRValidationError):
        ir.validate()


def test_markup_analysis_derives_tokens_breakpoints_and_components():
    ir = analyze_local_site(FIXTURE)
    assert ir.pages[0].title == "Nimbus Notes"
    assert len(ir.rules) > 10

    custom = {t.name: t.value for t in ir.tokens if t.kind == "custom"}
    assert custom["--brand"] == "#2f6f4e"

    colours = {t.value for t in ir.tokens if t.kind == "color"}
    assert "#2f6f4e" in colours
    assert "#ffffff" in colours

    kinds = {(b["kind"], b["value"]) for b in ir.breakpoints}
    assert ("min", 640.0) in kinds
    assert ("min", 1024.0) in kinds

    card = [c for c in ir.components if c.name == "card"]
    assert card and card[0].count == 3
    assert card[0].node_ids


def test_component_clustering_requires_repetition():
    markup = "<html><body><div class='only'>x</div></body></html>"
    root = parse_html(markup).root
    assert build_components(root, min_count=2) == []


def test_assets_are_discovered_with_metadata():
    ir = analyze_local_site(FIXTURE)
    urls = {a.url: a for a in ir.assets}
    assert "assets/hero.png" in urls
    assert "assets/hero@2x.png" in urls
    assert "assets/favicon.ico" in urls
    assert "styles/site.css" in urls
    assert "../assets/inter.woff2" in urls
    assert any(a.kind == "svg" for a in ir.assets)

    hero = urls["assets/hero.png"]
    assert hero.width == 960 and hero.height == 540
    assert hero.mime == "image/png"
    assert hero.licence == LicenceStatus.OWNED


def test_licence_defaults_to_unknown_for_external_assets():
    markup = "<html><body><img src='https://cdn.example.com/x.png'></body></html>"
    assets = discover_assets(parse_html(markup).root, [], owned=True)
    assert assets[0].licence == LicenceStatus.UNKNOWN


def test_codegen_is_deterministic_and_preserves_structure():
    ir = analyze_local_site(FIXTURE)
    first_html, second_html = codegen.to_html(ir), codegen.to_html(ir)
    assert first_html == second_html
    assert 'class="card"' in first_html
    assert first_html.count("<article") == 3

    css = codegen.to_css(ir)
    assert css == codegen.to_css(ir)
    assert "--brand: #2f6f4e;" in css
    assert "@media (min-width: 640px)" in css


def test_missing_structure_produces_warnings_not_silence():
    ir = analyze_markup("<html><head></head><body><p>bare</p></body></html>")
    joined = " ".join(ir.warnings)
    assert "no <title>" in joined
    assert "no <h1>" in joined
    assert "no stylesheets" in joined


def test_local_site_refuses_paths_outside_the_root():
    with pytest.raises(ValueError):
        analyze_local_site(FIXTURE, entry="../../../etc/passwd")


def test_write_outputs_creates_the_documented_set(tmp_path):
    ir = analyze_local_site(FIXTURE)
    files = write_outputs(ir, tmp_path)
    for key in ("ir", "tokens", "components", "assets", "html", "css", "design"):
        assert files[key].is_file()
    assert "Design tokens" in files["design"].read_text(encoding="utf-8")


def test_analysis_is_stable_across_runs():
    first = analyze_local_site(FIXTURE).to_dict()
    second = analyze_local_site(FIXTURE).to_dict()
    assert first["tokens"] == second["tokens"]
    assert first["components"] == second["components"]
    assert first["assets"] == second["assets"]
