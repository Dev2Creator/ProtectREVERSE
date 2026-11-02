"""Command-line interface: scan, inspect, explain, plan, serve."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .agentmd import MODES as AGENT_MODES, generate_agent_md
from .config import REPORT_DIR
from .evidence import Investigation
from .explain import MODES as EXPLAIN_MODES, explain
from .intake import open_target
from .planner import build_plan, render_plan_json, render_plan_markdown
from .security import UnsafeTarget
from .workspace import delete, export_reports, list_investigations, load, save


def _print(msg: str = "") -> None:
    print(msg)


def cmd_scan(args: argparse.Namespace) -> int:
    from .analyzers.local import analyze_target

    try:
        target = open_target(args.target)
    except UnsafeTarget as exc:
        _print(f"refused: {exc}")
        return 2

    try:
        inv = analyze_target(target)
    finally:
        target.dispose()

    save(inv)
    formats = [fmt.strip() for fmt in args.formats.split(",") if fmt.strip()]
    out_dir = Path(args.out) if args.out else Path(REPORT_DIR)
    written = export_reports(inv, formats, out_dir)

    if args.plan:
        plan = build_plan(inv)
        plan_path = out_dir / f"{inv.id}-plan.md"
        plan_path.write_text(render_plan_markdown(plan), encoding="utf-8")
        (out_dir / f"{inv.id}-plan.json").write_text(render_plan_json(plan), encoding="utf-8")
        written["plan"] = plan_path

    if args.agentmd:
        text = generate_agent_md(inv, args.agentmd)
        agent_path = out_dir / f"{inv.id}-AGENT.md"
        agent_path.write_text(text, encoding="utf-8")
        written["agentmd"] = agent_path

    if args.json_summary:
        _print(json.dumps({
            "investigation": inv.id,
            "target": inv.target,
            "counts": inv.to_dict()["counts"],
            "outputs": {k: str(v) for k, v in written.items()},
        }, indent=2))
        return 0

    counts = inv.to_dict()["counts"]["by_status"]
    _print(f"Investigation {inv.id} · {inv.target}")
    _print(f"Findings: {sum(counts.values())} "
           f"(observed {counts.get('OBSERVED', 0)}, inferred {counts.get('INFERRED', 0)}, "
           f"unknown {counts.get('UNKNOWN', 0)}, not checked {counts.get('NOT_CHECKED', 0)})")
    if inv.warnings:
        for warning in inv.warnings:
            _print(f"warning: {warning}")
    _print("")
    for fmt, path in written.items():
        _print(f"{fmt:8s} {path}")
    _print("")
    _print("Nothing was executed. Findings carry status and confidence; read the limitations section.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    rows = list_investigations()
    if not rows:
        _print("No investigations yet. Run: protectreverse scan <path|zip|git-url>")
        return 0
    for row in rows:
        _print(f"{row['id']}  {row['kind']:11s} {row['findings']:>3s} findings  {row['created_at']}  {row['target']}")
    return 0


def _load_or_fail(inv_id: str) -> Optional[Investigation]:
    try:
        return load(inv_id)
    except FileNotFoundError:
        _print(f"no such investigation: {inv_id}")
        return None


def cmd_show(args: argparse.Namespace) -> int:
    inv = _load_or_fail(args.investigation)
    if not inv:
        return 2
    for finding in inv.findings:
        _print(f"{finding.id}  {finding.status.value:12s} {finding.confidence.value:6s} {finding.category}")
        _print(f"     {finding.claim}")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    inv = _load_or_fail(args.investigation)
    if not inv:
        return 2
    try:
        _print(explain(inv, args.mode))
    except ValueError as exc:
        _print(str(exc))
        return 2
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    inv = _load_or_fail(args.investigation)
    if not inv:
        return 2
    plan = build_plan(inv)
    if args.json:
        _print(render_plan_json(plan))
    else:
        _print(render_plan_markdown(plan))
    return 0


def cmd_agentmd(args: argparse.Namespace) -> int:
    inv = _load_or_fail(args.investigation)
    if not inv:
        return 2
    try:
        _print(generate_agent_md(inv, args.mode))
    except ValueError as exc:
        _print(str(exc))
        return 2
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    removed = delete(args.investigation)
    _print("deleted" if removed else "nothing to delete")
    return 0 if removed else 2


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    serve(Path(args.out or REPORT_DIR), port=args.port)
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    _print(f"ProtectREVERSE {__version__}")
    _print("Licence: custom proprietary source-available EULA (LICENSE-EULA.md). AS IS.")
    return 0


def cmd_visual(args: argparse.Namespace) -> int:
    from .visual.pipeline import analyze_local_site, analyze_markup, write_outputs

    path = Path(args.path)
    try:
        if path.is_dir():
            ir = analyze_local_site(path, entry=args.entry)
        elif path.is_file():
            ir = analyze_markup(path.read_text(encoding="utf-8", errors="replace"), url=path.name)
        else:
            _print(f"not found: {path}")
            return 2
    except (ValueError, OSError) as exc:
        _print(f"refused: {exc}")
        return 2

    out_dir = Path(args.out or REPORT_DIR)
    files = write_outputs(ir, out_dir)

    if args.json_summary:
        _print(json.dumps({
            "page": ir.pages[0].url,
            "nodes": ir.node_total,
            "rules": len(ir.rules),
            "tokens": len(ir.tokens),
            "components": len(ir.components),
            "assets": len(ir.assets),
            "breakpoints": len(ir.breakpoints),
            "warnings": ir.warnings,
            "files": {key: str(value) for key, value in files.items()},
        }, indent=2))
        return 0

    _print(f"visual reconstruction of {path}")
    _print(
        f"nodes {ir.node_total} · rules {len(ir.rules)} · tokens {len(ir.tokens)} · "
        f"components {len(ir.components)} · assets {len(ir.assets)} · "
        f"breakpoints {len(ir.breakpoints)}"
    )
    for warning in ir.warnings:
        _print(f"warning: {warning}")
    for key, file in files.items():
        _print(f"{key:10} {file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="protectreverse",
        description="Evidence-first software intelligence for projects you are authorized to inspect.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="analyse a local directory, ZIP archive or public Git repository")
    scan.add_argument("target", help="path, .zip archive, or https git URL")
    scan.add_argument("--out", help="output directory (default: ~/.protectreverse/reports)")
    scan.add_argument("--formats", default="md,html,json", help="comma-separated: md,html,json")
    scan.add_argument("--plan", action="store_true", help="also write an implementation plan")
    scan.add_argument("--agentmd", choices=sorted(AGENT_MODES), help="also write AGENT.md in this mode")
    scan.add_argument("--json-summary", action="store_true", help="machine-readable summary on stdout")
    scan.set_defaults(func=cmd_scan)

    listing = sub.add_parser("list", help="list stored investigations")
    listing.set_defaults(func=cmd_list)

    show = sub.add_parser("show", help="print findings for an investigation")
    show.add_argument("investigation")
    show.set_defaults(func=cmd_show)

    exp = sub.add_parser("explain", help="explain an investigation in three registers")
    exp.add_argument("investigation")
    exp.add_argument("--mode", default="simple", choices=sorted(EXPLAIN_MODES))
    exp.set_defaults(func=cmd_explain)

    plan = sub.add_parser("plan", help="print the implementation plan")
    plan.add_argument("investigation")
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(func=cmd_plan)

    agent = sub.add_parser("agentmd", help="print an AGENT.md draft")
    agent.add_argument("investigation")
    agent.add_argument("--mode", default="understand", choices=sorted(AGENT_MODES))
    agent.set_defaults(func=cmd_agentmd)

    rm = sub.add_parser("delete", help="delete an investigation and its workspace")
    rm.add_argument("investigation")
    rm.set_defaults(func=cmd_delete)

    srv = sub.add_parser("serve", help="serve generated reports on localhost")
    srv.add_argument("--port", type=int, default=8787)
    srv.add_argument("--out", help="report directory to serve")
    srv.set_defaults(func=cmd_serve)

    vis = sub.add_parser(
        "visual",
        help="reconstruct DOM, CSS tokens, components and assets from markup",
    )
    vis.add_argument("path", help="site directory or single HTML file")
    vis.add_argument("--entry", default="index.html", help="entry file inside the site directory")
    vis.add_argument("--out", help="output directory (default: ~/.protectreverse/reports)")
    vis.add_argument("--json-summary", action="store_true", help="machine-readable summary on stdout")
    vis.set_defaults(func=cmd_visual)

    ver = sub.add_parser("version", help="print version and licence summary")
    ver.set_defaults(func=cmd_version)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
