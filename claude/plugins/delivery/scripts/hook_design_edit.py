#!/usr/bin/env python3
"""PostToolUse edit-time design-system warning (DRAFT, not wired in hooks/hooks.json).

When an Edit, MultiEdit or Write puts CSS or a hand-made button, table, tab row or progress bar into app code,
this prints one warning to the session: use the shared UI part instead. It only warns. It never blocks, never
writes a file and always exits 0 (every error is one line on stderr).

Active only in a project that has docs/design-system/ and only for files under the app paths. Defaults:
app paths `apps/`, shared UI paths `packages/ui/` (a file under a shared path is never warned about).
Override in .delivery/config.json:  "design_system": {"app_paths": ["apps/"], "shared_paths": ["packages/ui/"]}

It is the early warning. The no-app-CSS scan and the other kit tests are the gate (references/design-gate.md).
Disable: CLAUDE_DELIVERY_HOOKS=off. Standard library only.

Wire it (see the proposal) with a PostToolUse entry, matcher "Edit|MultiEdit|Write".
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

STYLE_FILE_RE = re.compile(r"\.(css|scss|sass|less)$", re.I)
SOURCE_FILE_RE = re.compile(r"\.(tsx?|jsx?|html|vue|svelte|mjs|cjs)$", re.I)

# (kind, pattern over the added text, what to use instead)
TEXT_CHECKS = [
    ("css-in-code", re.compile(r"<style[\s>]|createElement\(\s*['\"]style['\"]|\bstyled\s*[.(]|\bcss\s*`|\.insertRule\(|adoptedStyleSheets|\.style\.cssText"),
     "a style block in code: put the look in the shared UI package"),
    ("hand-made button", re.compile(r"<button[\s>]"), "a hand-made <button>: use the shared button part"),
    ("hand-made table", re.compile(r"<table[\s>]"), "a hand-made <table>: use the shared table part"),
    ("hand-made tab row", re.compile(r"role=[\"']tab(list)?[\"']"), "a hand-made tab row: use the shared tabs part"),
    ("hand-made progress bar", re.compile(r"<progress[\s>]|role=[\"']progressbar[\"']"), "a hand-made progress bar: use the shared progress part"),
]
STYLE_ATTR_RE = re.compile(r"(?<![\w-])style=(\{|\"|')")


def style_attr_sets_layout(text: str) -> bool:
    """True when a style= attribute sets anything but a CSS custom property (--name)."""
    for m in STYLE_ATTR_RE.finditer(text):
        rest = text[m.end(): m.end() + 300]
        value = rest.split("}")[0] if m.group(1) == "{" else rest.split(m.group(1))[0]
        keys = re.findall(r"(?:^|[{,;\s])['\"]?([a-zA-Z-][\w-]*)['\"]?\s*:", value)
        if any(not k.startswith("--") for k in keys):
            return True
    return False


def scan_added(path: str, added: str) -> list[str]:
    """The warnings for the text an edit adds to one file. Pure."""
    found: list[str] = []
    if STYLE_FILE_RE.search(path):
        return ["a stylesheet in app code: put the look in the shared UI package"]
    if not SOURCE_FILE_RE.search(path):
        return found
    for _kind, rx, advice in TEXT_CHECKS:
        if rx.search(added):
            found.append(advice)
    if style_attr_sets_layout(added):
        found.append("a style= attribute with layout or colour: use shared UI parts (custom properties only)")
    return found


def added_texts(tool: str, tool_input: dict) -> list[str]:
    if tool == "Write":
        return [str(tool_input.get("content", ""))]
    if tool == "Edit":
        return [str(tool_input.get("new_string", ""))]
    if tool == "MultiEdit":
        return [str(e.get("new_string", "")) for e in tool_input.get("edits", []) if isinstance(e, dict)]
    return []


def find_root(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / "docs" / "design-system").is_dir():
            return p
    return None


def load_paths(root: Path) -> tuple[list[str], list[str]]:
    app, shared = ["apps/"], ["packages/ui/"]
    try:
        cfg = json.loads((root / ".delivery" / "config.json").read_text(encoding="utf-8"))
        ds = cfg.get("design_system", {})
        app = [str(x) for x in ds.get("app_paths", app)]
        shared = [str(x) for x in ds.get("shared_paths", shared)]
    except (OSError, ValueError, AttributeError):
        pass
    return app, shared


def decide(data: dict) -> str | None:
    """The warning text for one hook input, or None. Pure apart from reading the config and folders."""
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}
    file_path = str(tool_input.get("file_path", ""))
    if tool not in ("Edit", "MultiEdit", "Write") or not file_path:
        return None
    path = Path(file_path)
    root = find_root(path.parent if path.is_absolute() else Path(data.get("cwd") or os.getcwd()))
    if root is None:
        return None
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix() if path.is_absolute() else path.as_posix()
    except ValueError:
        return None
    app, shared = load_paths(root)
    if not any(rel.startswith(a) for a in app) or any(rel.startswith(s) for s in shared):
        return None
    findings: list[str] = []
    for text in added_texts(tool, tool_input):
        for f in scan_added(rel, text):
            if f not in findings:
                findings.append(f)
    if not findings:
        return None
    return (
        f"Design system: this edit to {rel} adds " + "; ".join(findings) + ". "
        "Apps carry no CSS and no hand-made parts; the shared UI package owns every look "
        "(docs/design-system/). Use the shared part, or add it to the shared package first."
    )


def main() -> int:
    if os.environ.get("CLAUDE_DELIVERY_HOOKS", "").lower() == "off":
        return 0
    try:
        data = json.loads(sys.stdin.read() or "{}")
        message = decide(data)
        if message:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message}}))
    except Exception as e:  # noqa: BLE001
        print(f"luismc-delivery: design edit hook: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
