"""CSS reconstruction: rules, cascade metadata, custom properties and tokens.

Parsing is conservative. A declaration is reported exactly as authored, with
variables resolved through their fallback chain, and every derived token keeps
the usage count that justified it. Nothing here invents a value that does not
appear in the collected stylesheets.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .ir import Provenance, RuleIR, TokenIR

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_RGB = re.compile(r"rgba?\(([^)]*)\)")
_LENGTH = re.compile(r"(-?\d*\.?\d+)(px|rem|em)\b")
_MEDIA_WIDTH = re.compile(r"\(\s*(min|max)-width\s*:\s*([0-9.]+)\s*(px|rem|em)\s*\)")
_VAR_USE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*))?\)")
_VAR_DEF = re.compile(r"^--[\w-]+$")

_TOKEN_RE = re.compile(r"#[\w-]+|\.[\w-]+|\[[^\]]*\]|::[\w-]+|:[\w-]+|[a-zA-Z][\w-]*|\*")

SPACING_PROPS = {
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "gap", "row-gap", "column-gap",
}

COMPOUND_PROPS = {"box-shadow", "border-radius", "font-size", "font-family"}


def strip_comments(text: str) -> str:
    return _COMMENT.sub(" ", text)


def _split_top(text: str, separator: str) -> List[str]:
    """Split on a separator while ignoring separators inside brackets/quotes."""
    parts: List[str] = []
    depth = 0
    quote = ""
    buffer: List[str] = []
    for char in text:
        if quote:
            buffer.append(char)
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            buffer.append(char)
            continue
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(depth - 1, 0)
        if char == separator and depth == 0:
            parts.append("".join(buffer))
            buffer = []
            continue
        buffer.append(char)
    if buffer:
        parts.append("".join(buffer))
    return [p.strip() for p in parts if p.strip()]


def parse_declarations(body: str) -> Dict[str, str]:
    declarations: Dict[str, str] = {}
    for chunk in _split_top(body, ";"):
        prop, sep, value = chunk.partition(":")
        if not sep:
            continue
        prop = prop.strip().lower()
        value = " ".join(value.split())
        if prop and value:
            declarations[prop] = value
    return declarations


def specificity(selector: str) -> Tuple[int, int, int]:
    ids = classes = elements = 0
    for match in _TOKEN_RE.finditer(selector):
        token = match.group(0)
        if token.startswith("#"):
            ids += 1
        elif token.startswith(".") or token.startswith("["):
            classes += 1
        elif token.startswith("::"):
            elements += 1
        elif token.startswith(":"):
            classes += 1
        elif token == "*":
            continue
        else:
            elements += 1
    return (ids, classes, elements)


def parse_stylesheet(text: str, media: Optional[str] = None) -> List[RuleIR]:
    source = strip_comments(text)
    rules: List[RuleIR] = []
    cursor = 0
    length = len(source)
    while cursor < length:
        open_index = source.find("{", cursor)
        if open_index == -1:
            break
        head = source[cursor:open_index].strip()
        depth = 0
        scan = open_index
        while scan < length:
            if source[scan] == "{":
                depth += 1
            elif source[scan] == "}":
                depth -= 1
                if depth == 0:
                    break
            scan += 1
        body = source[open_index + 1:scan]
        cursor = scan + 1
        if not head:
            continue
        lowered = head.lower()

        if lowered.startswith("@media"):
            inner = head[len("@media"):].strip()
            combined = inner if media is None else f"{media} and {inner}"
            rules.extend(parse_stylesheet(body, combined))
            continue
        if lowered.startswith("@font-face"):
            rules.append(RuleIR(
                selector="@font-face",
                declarations=parse_declarations(body),
                media=media,
                specificity=(0, 0, 0),
            ))
            continue
        if lowered.startswith("@keyframes") or lowered.startswith("@-webkit-keyframes"):
            rules.append(RuleIR(selector=head, declarations={}, media=media, origin="keyframes"))
            continue
        if lowered.startswith(("@import", "@charset", "@namespace")):
            continue
        if lowered.startswith("@"):
            rules.extend(parse_stylesheet(body, media))
            continue

        declarations = parse_declarations(body)
        if not declarations:
            continue
        for selector in _split_top(head, ","):
            rules.append(RuleIR(
                selector=selector,
                declarations=dict(declarations),
                media=media,
                specificity=specificity(selector),
            ))
    return rules


def collect_variables(rules: List[RuleIR]) -> Dict[str, str]:
    variables: Dict[str, str] = {}
    for rule in rules:
        for prop, value in rule.declarations.items():
            if _VAR_DEF.match(prop):
                variables[prop] = value
    return variables


def resolve_value(value: str, variables: Dict[str, str], _seen: Optional[set] = None) -> str:
    seen = set() if _seen is None else _seen

    def replace(match: re.Match) -> str:
        name = match.group(1)
        fallback = match.group(2)
        if name in seen:
            return match.group(0)
        if name in variables:
            return resolve_value(variables[name], variables, seen | {name})
        if fallback is not None:
            return resolve_value(fallback.strip(), variables, seen | {name})
        return match.group(0)

    return _VAR_USE.sub(replace, value)


def apply_variables(rules: List[RuleIR]) -> Dict[str, str]:
    variables = collect_variables(rules)
    for rule in rules:
        rule.declarations = {
            prop: resolve_value(value, variables) for prop, value in rule.declarations.items()
        }
    return variables


def _normalise_colour(raw: str) -> Optional[str]:
    raw = raw.strip().lower()
    if raw.startswith("#"):
        digits = raw[1:]
        if len(digits) == 3:
            return "#" + "".join(ch * 2 for ch in digits)
        if len(digits) == 4:
            return "#" + "".join(ch * 2 for ch in digits[:3])
        if len(digits) == 6:
            return "#" + digits
        if len(digits) == 8:
            return "#" + digits if digits[6:] == "ff" else None
        return None
    match = _RGB.match(raw)
    if not match:
        return None
    parts = [p.strip() for p in match.group(1).split(",")]
    if len(parts) not in (3, 4):
        return None
    if len(parts) == 4 and parts[3] not in {"1", "1.0"}:
        return None
    try:
        channels = []
        for part in parts[:3]:
            number = float(part.rstrip("%"))
            if part.endswith("%"):
                number = number * 255 / 100
            channels.append(max(0, min(255, int(round(number)))))
    except ValueError:
        return None
    return "#" + "".join(f"{c:02x}" for c in channels)


def breakpoints(rules: List[RuleIR]) -> List[Dict[str, object]]:
    counts: Dict[Tuple[str, float, str], int] = {}
    for rule in rules:
        if not rule.media:
            continue
        for kind, number, unit in _MEDIA_WIDTH.findall(rule.media):
            key = (kind, float(number), unit)
            counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (item[0][2], item[0][1], item[0][0]))
    return [
        {"kind": kind, "value": number, "unit": unit, "rules": count}
        for (kind, number, unit), count in ordered
    ]


def derive_tokens(rules: List[RuleIR], variables: Optional[Dict[str, str]] = None) -> List[TokenIR]:
    colours: Dict[str, int] = {}
    spacing: Dict[str, int] = {}
    radii: Dict[str, int] = {}
    type_sizes: Dict[str, int] = {}
    families: Dict[str, int] = {}
    shadows: Dict[str, int] = {}

    def bump(bucket: Dict[str, int], key: str) -> None:
        bucket[key] = bucket.get(key, 0) + 1

    for rule in rules:
        for prop, value in rule.declarations.items():
            for raw in _HEX.findall(value):
                colour = _normalise_colour(raw)
                if colour:
                    bump(colours, colour)
            for match in _RGB.finditer(value):
                colour = _normalise_colour(match.group(0))
                if colour:
                    bump(colours, colour)
            if prop in SPACING_PROPS:
                for number, unit in _LENGTH.findall(value):
                    bump(spacing, f"{_trim_number(number)}{unit}")
            if prop == "border-radius":
                for part in _split_top(value, " "):
                    for number, unit in _LENGTH.findall(part):
                        bump(radii, f"{_trim_number(number)}{unit}")
                    if part in {"0", "50%"}:
                        bump(radii, part)
            if prop == "font-size":
                bump(type_sizes, value)
            if prop == "font-family":
                first = _split_top(value, ",")[0].strip().strip("\"'").lower()
                if first:
                    bump(families, first)
            if prop == "box-shadow" and value.lower() != "none":
                bump(shadows, value)

    tokens: List[TokenIR] = []

    if variables:
        usage: Dict[str, int] = {}
        for rule in rules:
            for value in rule.declarations.values():
                for match in _VAR_USE.finditer(value):
                    usage[match.group(1)] = usage.get(match.group(1), 0) + 1
        for name in sorted(variables):
            tokens.append(TokenIR(
                kind="custom",
                name=name,
                value=variables[name],
                usage=max(usage.get(name, 0), 1),
                provenance=Provenance.OBSERVED,
            ))

    for kind, bucket, prefix in (
        ("color", colours, "color"),
        ("space", spacing, "space"),
        ("radius", radii, "radius"),
        ("type", type_sizes, "type"),
        ("font", families, "font"),
        ("shadow", shadows, "shadow"),
    ):
        ordered = sorted(bucket.items(), key=lambda item: (-item[1], item[0]))
        for index, (value, count) in enumerate(ordered, start=1):
            tokens.append(TokenIR(
                kind=kind,
                name=f"{prefix}-{index}",
                value=value,
                usage=count,
                provenance=Provenance.OBSERVED,
            ))
    return tokens


def _trim_number(raw: str) -> str:
    try:
        number = float(raw)
    except ValueError:
        return raw
    if number == int(number):
        return str(int(number))
    return f"{number:g}"
