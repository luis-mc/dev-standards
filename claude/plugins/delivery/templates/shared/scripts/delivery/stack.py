#!/usr/bin/env python3
"""The declared stack of a project (DL406, owner decision D316).

    stack.py [--root DIR] [--json]

A project may declare its tools in the `stack` block of .delivery/config.json. This module finds the tools a
repository uses from its files, compares them with the declaration and with the tools the plugin's checks
handle (KNOWN), and says for each tool: known, declared or unchecked. An unchecked tool is one the plugin
cannot judge and the project did not declare; `delivery_doctor.py` fails on it (check `stack.tools`).

Standard library only. Importable by the other scripts.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys

# The tools the checks handle today, and where. Keep this list in step with the code it cites.
KNOWN = {
    "playwright": "test_guardrails.py G1 (config timeout) and the retry check, e2e_push_check.py",
    "vitest": "test_guardrails.py G1 (vitest.config timeout)",
    "jest": "test_guardrails.py G1 (testTimeout in jest config or package.json), retryTimes",
    "pytest": "test_guardrails.py G1 (pytest-timeout), reruns, parametrize; rerun_tests.py",
    "go": "delivery_common.py package kind go-modules; rerun_tests.py",
    "cargo": "test_guardrails.py (cargo test timeout), delivery_common.py cargo-workspace, rust_ci.py",
    "dotnet": "delivery_common.py package kind dotnet-sln",
    "pnpm": "delivery_common.py pnpm-workspace, pnpm-lock.yaml scope",
}

# With no `stack` block, the track preset stands as the declaration (nothing changes for default projects).
PRESETS = {
    "ts": {"e2e": ["playwright"], "unit": ["vitest", "jest"], "package_manager": "pnpm"},
    "go": {"unit": ["go"], "build": ["go"]},
    "rust": {"unit": ["cargo"], "build": ["cargo"]},
    "dotnet": {"unit": ["dotnet"], "build": ["dotnet"]},
}

LIST_FIELDS = ("e2e", "unit", "build", "e2e_spec_globs", "test_globs")
FIELDS = LIST_FIELDS + ("package_manager",)
TOOL_FIELDS = ("e2e", "unit", "build")

_SKIP = {".git", "node_modules", "target", "dist", "build", "vendor", ".venv", "venv", "__pycache__", ".tox", ".delivery"}
_MAX_DEPTH = 2


def _files(root):
    """Relative paths (forward slashes) up to two folders deep, without dependency and build folders."""
    out = []
    root = os.path.abspath(root)
    for dirpath, dirs, names in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dirs[:] = sorted(d for d in dirs if d not in _SKIP)
        if depth >= _MAX_DEPTH:
            dirs[:] = []
        for n in sorted(names):
            out.append(n if rel == "." else (rel + "/" + n).replace(os.sep, "/"))
    return out


def _text(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def detect_tools(root):
    """{tool: evidence_path} found from files; the first (shallowest) file wins."""
    found = {}

    def add(tool, rel):
        found.setdefault(tool, rel)

    for rel in _files(root):
        base = rel.rsplit("/", 1)[-1]
        if re.match(r"cypress\.config\.", base):
            add("cypress", rel)
        elif re.match(r"playwright\.config\.", base):
            add("playwright", rel)
        elif re.match(r"vitest\.config\.", base):
            add("vitest", rel)
        elif re.match(r"jest\.config\.", base):
            add("jest", rel)
        elif base == "package.json":
            try:
                data = json.loads(_text(root, rel))
            except ValueError:
                data = None
            if isinstance(data, dict) and "jest" in data:
                add("jest", rel)
        elif base in ("pytest.ini", "conftest.py"):
            add("pytest", rel)
        elif base == "pyproject.toml":
            text = _text(root, rel)
            if re.search(r"^\s*\[tool\.pytest", text, re.M):
                add("pytest", rel)
            if re.search(r"\bselenium\b", text, re.I):
                add("selenium", rel)
        elif re.match(r"requirements[^/]*\.txt$", base):
            if re.search(r"^\s*selenium\b", _text(root, rel), re.I | re.M):
                add("selenium", rel)
        elif base == "pnpm-lock.yaml":
            add("pnpm", rel)
        elif base == "yarn.lock":
            add("yarn", rel)
        elif base == "package-lock.json":
            add("npm", rel)
        elif base == "go.mod":
            add("go", rel)
        elif base == "Cargo.toml":
            add("cargo", rel)
        elif base.endswith((".csproj", ".sln")):
            add("dotnet", rel)
        elif base.startswith("build.gradle"):
            add("gradle", rel)
        elif base == "pom.xml":
            add("maven", rel)
        elif base == "Gemfile":
            add("bundler", rel)
        elif base == "composer.json":
            add("composer", rel)
    return found


def declared(cfg):
    """The `stack` block of the config ({} when absent or not an object)."""
    block = (cfg or {}).get("stack")
    return block if isinstance(block, dict) else {}


def problems(cfg):
    """Faults in the stack block: unknown fields, wrong types. [] when it is fine."""
    block = (cfg or {}).get("stack")
    if block is None:
        return []
    if not isinstance(block, dict):
        return ["stack: expected an object"]
    out = []
    for k, v in block.items():
        if k.startswith("_"):
            continue
        if k not in FIELDS:
            out.append("stack.%s: unknown field (allowed: %s)" % (k, ", ".join(FIELDS)))
        elif k == "package_manager":
            if not isinstance(v, str):
                out.append("stack.package_manager: expected a string")
        elif not (isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)):
            out.append("stack.%s: expected a list of strings" % k)
    return out


def declared_tools(cfg):
    """The tool names the stack block declares (lower case)."""
    block = declared(cfg)
    names = set()
    for f in TOOL_FIELDS:
        v = block.get(f)
        if isinstance(v, list):
            names.update(x.strip().lower() for x in v if isinstance(x, str) and x.strip())
    pm = block.get("package_manager")
    if isinstance(pm, str) and pm.strip():
        names.add(pm.strip().lower())
    return names


def tracks(root):
    """Tracks named by scripts/delivery/gate.json (a string, comma list or list)."""
    try:
        with open(os.path.join(root, "scripts", "delivery", "gate.json"), encoding="utf-8") as f:
            val = json.load(f).get("track")
    except (OSError, ValueError, AttributeError):
        return []
    names = val.split(",") if isinstance(val, str) else val if isinstance(val, list) else []
    return [n.strip() for n in names if isinstance(n, str) and n.strip() in PRESETS]


def preset_tools(root):
    names = set()
    for t in tracks(root):
        p = PRESETS[t]
        for f in TOOL_FIELDS:
            names.update(p.get(f, []))
        if p.get("package_manager"):
            names.add(p["package_manager"])
    return names


def resolve(root, cfg):
    """{tool: {"status": known|declared|unchecked, "evidence": path|None, "judged": bool}}.

    Declared tools (the block, or the track preset when there is no block) come first and win over detection.
    `judged` is True when the plugin's checks handle the tool (it is in KNOWN)."""
    found = detect_tools(root)
    decl = declared_tools(cfg) if declared(cfg) else set()
    # With no block the track preset stands as the declaration; its tools are all KNOWN, so they print as known.
    out = {}
    for tool, ev in found.items():
        if tool in decl:
            status = "declared"
        elif tool in KNOWN:
            status = "known"
        else:
            status = "unchecked"
        out[tool] = {"status": status, "evidence": ev, "judged": tool in KNOWN}
    for tool in sorted(decl - set(out)):
        out[tool] = {"status": "declared", "evidence": None, "judged": tool in KNOWN}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="stack.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    cfg = {}
    try:
        with open(os.path.join(args.root, ".delivery", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        pass
    res = resolve(args.root, cfg)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        for tool, r in sorted(res.items()):
            print("%-12s %-10s %s" % (tool, r["status"], r["evidence"] or ""))
    return 1 if any(r["status"] == "unchecked" for r in res.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
