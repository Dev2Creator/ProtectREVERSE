"""Visual, DOM, CSS and asset reverse engineering engine.

Public surface:

    analyze_markup(markup, stylesheets) -> VisualIR
    analyze_local_site(root, entry)     -> VisualIR
    write_outputs(ir, out_dir)          -> generated files

Offline only in this milestone. Browser-level collection (computed styles,
rendered layout, states, screenshots) is specified in VISUAL_ENGINE_PLAN.md.
"""

from .css import (
    apply_variables,
    breakpoints,
    derive_tokens,
    parse_stylesheet,
    resolve_value,
    specificity,
)
from .dom import parse_html
from .ir import (
    AssetIR,
    ComponentIR,
    IRValidationError,
    IR_VERSION,
    LicenceStatus,
    NodeIR,
    PageIR,
    Provenance,
    RuleIR,
    TokenIR,
    VisualIR,
)
from .pipeline import (
    VisualAnalysis,
    analyze_and_emit,
    analyze_local_site,
    analyze_markup,
    render_design_system,
    write_outputs,
)

__all__ = [
    "AssetIR",
    "ComponentIR",
    "IRValidationError",
    "IR_VERSION",
    "LicenceStatus",
    "NodeIR",
    "PageIR",
    "Provenance",
    "RuleIR",
    "TokenIR",
    "VisualAnalysis",
    "VisualIR",
    "analyze_and_emit",
    "analyze_local_site",
    "analyze_markup",
    "apply_variables",
    "breakpoints",
    "derive_tokens",
    "parse_html",
    "parse_stylesheet",
    "render_design_system",
    "resolve_value",
    "specificity",
    "write_outputs",
]
