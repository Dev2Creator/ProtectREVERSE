"""Investigation persistence: save, list, load, delete.

Workspaces are plain JSON directories under ~/.protectreverse/workspaces so that
"delete my data" is a single, verifiable filesystem operation.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

from .config import REPORT_DIR, WORKSPACE_DIR
from .evidence import Investigation
from .reporting import render_html, render_json, render_markdown


def _workspace_path(inv_id: str) -> Path:
    return Path(WORKSPACE_DIR) / inv_id


def save(inv: Investigation) -> Path:
    path = _workspace_path(inv.id)
    path.mkdir(parents=True, exist_ok=True)
    target = path / "investigation.json"
    target.write_text(inv.to_json(), encoding="utf-8")
    return target


def load(inv_id: str) -> Investigation:
    path = _workspace_path(inv_id) / "investigation.json"
    if not path.is_file():
        raise FileNotFoundError(f"no investigation {inv_id}")
    return Investigation.from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_investigations() -> List[Dict[str, str]]:
    root = Path(WORKSPACE_DIR)
    if not root.is_dir():
        return []
    rows: List[Dict[str, str]] = []
    for entry in sorted(root.iterdir()):
        data_file = entry / "investigation.json"
        if not data_file.is_file():
            continue
        try:
            data = json.loads(data_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append({
            "id": data.get("id", entry.name),
            "target": data.get("target", "?"),
            "kind": data.get("target_kind", "?"),
            "created_at": data.get("created_at", "?"),
            "findings": str(data.get("counts", {}).get("findings", 0)),
        })
    return rows


def delete(inv_id: str) -> bool:
    path = _workspace_path(inv_id)
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True


def export_reports(inv: Investigation, formats: List[str], out_dir: Path) -> Dict[str, Path]:
    """Write selected formats and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}
    stem = f"{inv.id}-report"
    for fmt in formats:
        if fmt == "md":
            path = out_dir / f"{stem}.md"
            path.write_text(render_markdown(inv), encoding="utf-8")
        elif fmt == "html":
            path = out_dir / f"{stem}.html"
            path.write_text(render_html(inv), encoding="utf-8")
        elif fmt == "json":
            path = out_dir / f"{stem}.json"
            path.write_text(render_json(inv), encoding="utf-8")
        else:
            continue
        written[fmt] = path
    return written
