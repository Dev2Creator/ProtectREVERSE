"""Asset discovery from markup and stylesheets.

Metadata only by default. Nothing is downloaded: a reference is recorded with
its declared type, declared dimensions and a licence status that starts at
UNKNOWN unless the caller has established ownership of the source. The licence
gate exists so that an export cannot silently redistribute someone else's work.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .ir import AssetIR, LicenceStatus, NodeIR, RuleIR

MIME_BY_EXT: Dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "avif": "image/avif",
    "svg": "image/svg+xml",
    "ico": "image/x-icon",
    "woff": "font/woff",
    "woff2": "font/woff2",
    "ttf": "font/ttf",
    "otf": "font/otf",
    "eot": "application/vnd.ms-fontobject",
    "mp4": "video/mp4",
    "webm": "video/webm",
    "ogv": "video/ogg",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "css": "text/css",
    "js": "text/javascript",
    "mjs": "text/javascript",
    "json": "application/json",
    "webmanifest": "application/manifest+json",
}

_CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)")


def guess_mime(url: str) -> str:
    path = url.split("?", 1)[0].split("#", 1)[0]
    extension = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return MIME_BY_EXT.get(extension, "")


def is_external(url: str) -> bool:
    return url.startswith(("http://", "https://", "//"))


def _int_or_none(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    digits = value.strip().lower().removesuffix("px")
    try:
        return int(float(digits))
    except ValueError:
        return None


def _srcset_urls(raw: str) -> List[str]:
    urls = []
    for candidate in raw.split(","):
        parts = candidate.strip().split()
        if parts:
            urls.append(parts[0])
    return urls


class _Collector:
    def __init__(self, owned: bool) -> None:
        self.owned = owned
        self._items: Dict[Tuple[str, str], AssetIR] = {}

    def add(
        self,
        url: str,
        kind: str,
        *,
        used_in: str,
        mime: str = "",
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> None:
        url = (url or "").strip()
        if not url or url.startswith(("data:", "javascript:", "mailto:", "#")):
            return
        key = (url, kind)
        existing = self._items.get(key)
        if existing is None:
            licence = LicenceStatus.OWNED if (self.owned and not is_external(url)) else LicenceStatus.UNKNOWN
            existing = AssetIR(
                url=url,
                kind=kind,
                mime=mime or guess_mime(url),
                width=width,
                height=height,
                licence=licence,
            )
            self._items[key] = existing
        else:
            if existing.width is None and width is not None:
                existing.width = width
            if existing.height is None and height is not None:
                existing.height = height
            if not existing.mime and (mime or guess_mime(url)):
                existing.mime = mime or guess_mime(url)
        if used_in not in existing.used_in:
            existing.used_in.append(used_in)

    def results(self) -> List[AssetIR]:
        return sorted(self._items.values(), key=lambda a: (a.kind, a.url))


def discover_assets(root: NodeIR, rules: Optional[List[RuleIR]] = None, *, owned: bool = True) -> List[AssetIR]:
    collector = _Collector(owned)

    for node in root.walk():
        tag = node.tag
        attrs = node.attrs
        ref = node.selector or node.node_id

        if tag == "img":
            collector.add(
                attrs.get("src", ""),
                "image",
                used_in=ref,
                width=_int_or_none(attrs.get("width")),
                height=_int_or_none(attrs.get("height")),
            )
            for url in _srcset_urls(attrs.get("srcset", "")):
                collector.add(url, "image", used_in=ref)
        elif tag == "source":
            for url in _srcset_urls(attrs.get("srcset", "")):
                collector.add(url, "image", used_in=ref)
            collector.add(attrs.get("src", ""), "media", used_in=ref)
        elif tag == "video":
            collector.add(attrs.get("src", ""), "video", used_in=ref)
            collector.add(attrs.get("poster", ""), "image", used_in=ref)
        elif tag == "audio":
            collector.add(attrs.get("src", ""), "audio", used_in=ref)
        elif tag == "iframe":
            collector.add(attrs.get("src", ""), "document", used_in=ref)
        elif tag == "script":
            collector.add(attrs.get("src", ""), "script", used_in=ref)
        elif tag == "svg":
            collector.add(f"inline:svg:{node.node_id}", "svg", used_in=ref, mime="image/svg+xml")
        elif tag == "link":
            rel = attrs.get("rel", "").lower()
            href = attrs.get("href", "")
            if "icon" in rel:
                collector.add(href, "favicon", used_in=ref)
            elif "stylesheet" in rel:
                collector.add(href, "stylesheet", used_in=ref)
            elif "manifest" in rel:
                collector.add(href, "manifest", used_in=ref)
            elif "preload" in rel and attrs.get("as") == "font":
                collector.add(href, "font", used_in=ref)

    for rule in rules or []:
        for prop, value in rule.declarations.items():
            for url in _CSS_URL.findall(value):
                if rule.selector == "@font-face" or prop == "src":
                    collector.add(url, "font", used_in="@font-face")
                elif "background" in prop:
                    collector.add(url, "image", used_in=rule.selector)
                else:
                    collector.add(url, "asset", used_in=rule.selector)

    return collector.results()
