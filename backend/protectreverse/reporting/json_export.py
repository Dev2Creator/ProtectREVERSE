"""JSON export: the machine-readable investigation bundle."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .. import __version__
from ..evidence import Investigation


def render_json(inv: Investigation) -> str:
    payload = inv.to_dict()
    payload["tool"] = {"name": "ProtectREVERSE", "version": __version__}
    payload["exported_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload["disclaimer"] = (
        "Static analysis is not proof of runtime behaviour. Status and confidence "
        "travel with every finding. Provided AS IS; see LICENSE-EULA.md."
    )
    return json.dumps(payload, indent=2, ensure_ascii=False)
