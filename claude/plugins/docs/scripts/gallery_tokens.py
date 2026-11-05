"""gallery_tokens: read tokens.md and do the WCAG 2.2 contrast math for the design-system gallery (DOCSPEC section 15).

Standard library only. The parser is tolerant: a table is read when its header starts with Token (or Role / Tone); a missing
column, an empty cell or an unknown shape never raises, it just leaves the token without a value.
"""
from __future__ import annotations

import math
import re

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\Z")
SIZE_RE = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:px|rem|em|%|ms|s)?\Z")
SHADOW_RE = re.compile(r"-?\d+(?:px)?(?:\s+-?\d+(?:px)?){1,3}\s+rgba?\([\d.,\s]+\)\Z")
PREFIX_RE = re.compile(r"\*\*Prefix:\*\*\s*`([^`]+)`")
DARK_HEADS = ("dark",)
LIGHT_HEADS = ("light", "value", "comfortable")


def _cells(line: str) -> list:
    return [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]


def is_hex(v) -> bool:
    return bool(v) and bool(HEX_RE.match(v))


def is_size(v) -> bool:
    return bool(v) and bool(SIZE_RE.match(v))


def is_shadow(v) -> bool:
    return bool(v) and bool(SHADOW_RE.match(v))


def rgb(v: str) -> tuple:
    h = v.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(v: str) -> float:
    """WCAG 2.2 relative luminance of a #rgb or #rrggbb colour."""
    def lin(x):
        x /= 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in rgb(v))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def ratio_text(r: float) -> str:
    """One decimal, rounded down, so 4.47 never shows as a pass-looking 4.5."""
    return f"{math.floor(r * 10) / 10:.1f}:1"


class Tokens:
    """Token values by name (full name, prefix included): {'light': str, 'dark': str|None, 'use': str}."""

    def __init__(self, text: str = ""):
        self.prefix = "--ds-"
        self.values: dict = {}
        self.roles: dict = {}   # role name -> {'size': token, 'weight': str, 'ceiling': str, 'family': token}
        self.widths: dict = {}  # per-width token -> [(column title, value)]
        self.edges: dict = {}   # tone name -> edge text, e.g. '3px solid'
        self._parse(text or "")

    def _parse(self, text: str) -> None:
        m = PREFIX_RE.search(text)
        if m:
            self.prefix = m.group(1)
        lines = text.splitlines()
        i = 0
        in_code = False
        while i < len(lines):
            ln = lines[i]
            if ln.startswith("```"):
                in_code = not in_code
            if in_code or not ln.startswith("|"):
                i += 1
                continue
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            rows = [r for r in rows if not all(re.fullmatch(r":?-{1,}:?", c or "-") for c in r)]
            if len(rows) < 2:
                continue
            head = [h.lower() for h in rows[0]]
            if head[0] == "token":
                self._token_table(head, rows[1:])
            elif head[0] == "role":
                ci = head.index("ceiling") if "ceiling" in head else None
                fi = head.index("family") if "family" in head else 3
                for r in rows[1:]:
                    if len(r) >= 4 and fi < len(r):
                        ceil = r[ci] if ci is not None and ci < len(r) else ""
                        self.roles[r[0]] = {"size": r[1], "weight": r[2], "ceiling": ceil, "family": r[fi]}
            elif head[0] == "tone" and len(head) >= 2 and head[1] == "edge":
                for r in rows[1:]:
                    if len(r) >= 2:
                        self.edges[r[0].lower()] = r[1]

    def _token_table(self, head: list, rows: list) -> None:
        def col(names):
            for n in names:
                if n in head:
                    return head.index(n)
            return None
        li, di, ui = col(LIGHT_HEADS), col(DARK_HEADS), col(("use",))
        if li is None:
            if ui is not None and len(head) > 2:  # a per-width table: one value column per width
                for r in rows:
                    if r and r[0].startswith("--") and r[0] not in self.widths:
                        self.widths[r[0]] = [(head[k], r[k]) for k in range(1, min(ui, len(r)))]
            return
        for r in rows:
            if not r or not r[0].startswith("--") or r[0] in self.values:
                continue  # first table wins (the density table repeats names)
            get = lambda k: (r[k] if k is not None and k < len(r) else "")  # noqa: E731
            self.values[r[0]] = {"light": get(li), "dark": get(di) or None, "use": get(ui)}

    def name(self, short: str) -> str:
        return self.prefix + short

    def value(self, short: str, theme: str = "light") -> str:
        v = self.values.get(self.name(short))
        if not v:
            return ""
        if theme == "dark" and v["dark"]:
            return v["dark"]
        return v["light"]

    def has_dark(self) -> bool:
        return any(is_hex(v["dark"]) for v in self.values.values() if v["dark"])

    def fill_pairs(self) -> list:
        """[(text short name, fill short name)] for each on-fill and on-tint pair, e.g. ('color-on-done', 'color-done')."""
        out = []
        for n in self.values:
            short = n[len(self.prefix):]
            m = re.fullmatch(r"color-on-(.+)", short)
            if m and ("color-" + m.group(1)) in {k[len(self.prefix):] for k in self.values}:
                out.append((short, "color-" + m.group(1)))
        return out

    def with_prefix(self, start: str) -> list:
        """[(short name, light value, use)] of every token whose short name starts with `start`."""
        return [(n[len(self.prefix):], v["light"], v["use"]) for n, v in self.values.items() if n.startswith(self.prefix + start)]
