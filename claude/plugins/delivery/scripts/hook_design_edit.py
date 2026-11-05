#!/usr/bin/env python3
"""PreToolUse edit-time design-system guard for Edit, MultiEdit and Write (owner decision D231).

When an edit would put CSS or a hand-made button, table, tab row or progress bar into app code, the first such
edit in a turn gets a warning only, no permission decision, so the normal permission rules apply (use the shared UI part instead); a repeat in the same turn is denied.
It writes no project file and every error is one line on stderr (the edit then goes through).

A turn is the time between two user prompts (or stops). The hook counts breaches per session in a small state
file in the temp folder (override the folder with CLAUDE_DESIGN_EDIT_STATE_DIR) and clears the count when it
is run for UserPromptSubmit or Stop (both are wired in hooks.json).

It judges what an edit adds: a check fires only when its matches increase from the old text to the new text
(Write: the file on disk). A new stylesheet is a breach; an Edit to an existing one is not. Test files are skipped.

Active only in a project that has docs/design-system/ and only for files under the app paths. Defaults:
app paths `apps/`, shared UI paths `packages/ui/` (a file under a shared path is never judged).
Set them in .delivery/config.json (schema: design_system.app_paths, design_system.shared_paths):
    "design_system": {"app_paths": ["apps/"], "shared_paths": ["packages/ui/"]}

It is the early guard. The no-app-CSS scan and the other kit tests are the gate (references/design-gate.md).
Disable: CLAUDE_DELIVERY_HOOKS=off. Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
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


def style_attr_layout_count(text: str) -> int:
    """How many style= attributes set anything but a CSS custom property (--name)."""
    n = 0
    for m in STYLE_ATTR_RE.finditer(text):
        rest = text[m.end(): m.end() + 300]
        value = rest.split("}")[0] if m.group(1) == "{" else rest.split(m.group(1))[0]
        keys = re.findall(r"(?:^|[{,;\s])['\"]?([a-zA-Z-][\w-]*)['\"]?\s*:", value)
        if any(not k.startswith("--") for k in keys):
            n += 1
    return n


def style_attr_sets_layout(text: str) -> bool:
    """True when a style= attribute sets anything but a CSS custom property (--name)."""
    return style_attr_layout_count(text) > 0


def is_test_file(path: str) -> bool:
    """A test file: *.test.*, *.spec.*, or under a __tests__ or tests folder. Never judged."""
    parts = path.replace("\\", "/").split("/")
    name = parts[-1].lower()
    return bool(re.search(r"\.(test|spec)\.", name)) or any(p in ("__tests__", "tests") for p in parts[:-1])


def scan_added(path: str, added: str, old: str = "", new_file: bool = False) -> list[str]:
    """The warnings for what an edit adds to one file: a check fires only when its matches increase
    from the old text to the new text. A stylesheet is a breach only when the file is new. Pure."""
    found: list[str] = []
    if STYLE_FILE_RE.search(path):
        return ["a stylesheet in app code: put the look in the shared UI package"] if new_file else found
    if not SOURCE_FILE_RE.search(path):
        return found
    for _kind, rx, advice in TEXT_CHECKS:
        if len(rx.findall(added)) > len(rx.findall(old)):
            found.append(advice)
    if style_attr_layout_count(added) > style_attr_layout_count(old):
        found.append("a style= attribute with layout or colour: use shared UI parts (custom properties only)")
    return found


def edit_texts(tool: str, tool_input: dict, current: str = "") -> list[tuple[str, str]]:
    """(old text, new text) pairs. Write: the file on disk (empty if absent) and the content."""
    if tool == "Write":
        return [(current, str(tool_input.get("content", "")))]
    if tool == "Edit":
        return [(str(tool_input.get("old_string", "")), str(tool_input.get("new_string", "")))]
    if tool == "MultiEdit":
        return [(str(e.get("old_string", "")), str(e.get("new_string", "")))
                for e in tool_input.get("edits", []) if isinstance(e, dict)]
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
    if is_test_file(rel):
        return None
    current, new_file = "", False
    if tool == "Write":
        target = path if path.is_absolute() else root / path
        try:
            current = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            new_file = True
    findings: list[str] = []
    for old, text in edit_texts(tool, tool_input, current):
        for f in scan_added(rel, text, old, new_file):
            if f not in findings:
                findings.append(f)
    if not findings:
        return None
    return (
        f"Design system: this edit to {rel} adds " + "; ".join(findings) + ". "
        "Apps carry no CSS and no hand-made parts; the shared UI package owns every look "
        "(docs/design-system/). Use the shared part, or add it to the shared package first."
    )


def state_file(session: str) -> Path:
    base = Path(os.environ.get("CLAUDE_DESIGN_EDIT_STATE_DIR") or tempfile.gettempdir())
    return base / ("luismc-design-edit-%s.json" % hashlib.sha1((session or "none").encode("utf-8")).hexdigest()[:16])


def read_count(session: str) -> int:
    try:
        return int(json.loads(state_file(session).read_text(encoding="utf-8")).get("breaches", 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return 0


def write_count(session: str, n: int) -> None:
    f = state_file(session)
    try:
        if n <= 0:
            f.unlink(missing_ok=True)
        else:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"breaches": n}), encoding="utf-8")
    except OSError:
        pass


def respond(data: dict) -> dict | None:
    """The hook output for one input, or None to let the tool run unannounced. Counts breaches per turn."""
    event = data.get("hook_event_name", "PreToolUse")
    session = str(data.get("session_id", ""))
    if event in ("UserPromptSubmit", "Stop", "SessionStart"):
        write_count(session, 0)  # a new turn: the count starts again
        return None
    message = decide(data)
    if not message:
        return None
    n = read_count(session)
    write_count(session, n + 1)
    if n == 0:
        # No permissionDecision: an "allow" would skip the user's permission prompt.
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "additionalContext": "Warning (first breach this turn; a repeat is denied). " + message}}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": "Denied (repeat breach this turn). " + message}}


def main() -> int:
    if os.environ.get("CLAUDE_DELIVERY_HOOKS", "").lower() == "off":
        return 0
    try:
        data = json.loads(sys.stdin.read() or "{}")
        out = respond(data)
        if out:
            print(json.dumps(out))
    except Exception as e:  # noqa: BLE001
        print(f"luismc-delivery: design edit hook: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
