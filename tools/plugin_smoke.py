#!/usr/bin/env python3
"""Plugin smoke: the DL-18 smoke for dev-standards, which deploys nothing.

For every plugin under claude/plugins/*/ it checks:
  - .claude-plugin/plugin.json parses and has name and version;
  - every script a hooks/hooks.json command names under the plugin exists;
  - every scripts/*.py compiles, and a script with an argparse CLI answers --help with exit 0;
  - every skills/*/SKILL.md has front matter with a description (name is optional, D128).
One line per plugin; exit 1 on any failure. Standard library only.

Usage: python tools/plugin_smoke.py [PLUGINS_DIR]
"""
from __future__ import annotations

import json
import os
import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HELP_TIMEOUT = 30
# Scripts whose --help is skipped, with the reason. Keep this short.
SKIP_HELP: dict[str, str] = {}
SCRIPT_REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)|\$CLAUDE_PLUGIN_ROOT/([\w./-]+)")


def _commands(node):
    """Every "command" string in a hooks.json value."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "command" and isinstance(v, str):
                yield v
            else:
                yield from _commands(v)
    elif isinstance(node, list):
        for v in node:
            yield from _commands(v)


def check_manifest(plugin: Path) -> list[str]:
    path = plugin / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return ["plugin.json: unreadable or bad JSON (%s)" % e]
    if not isinstance(data, dict):
        return ["plugin.json: not an object"]
    return ["plugin.json: no %s" % k for k in ("name", "version") if not data.get(k)]


def check_hooks(plugin: Path) -> list[str]:
    path = plugin / "hooks" / "hooks.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return ["hooks/hooks.json: bad JSON (%s)" % e]
    out = []
    for cmd in _commands(data):
        for m in SCRIPT_REF.finditer(cmd):
            rel = (m.group(1) or m.group(2)).rstrip(".")
            if not (plugin / rel).exists():
                out.append("hooks/hooks.json: missing script %s" % rel)
    return sorted(set(out))


def has_cli(src: str) -> bool:
    return "argparse" in src and "ArgumentParser" in src


def check_scripts(plugin: Path) -> list[str]:
    out = []
    scripts = plugin / "scripts"
    if not scripts.is_dir():
        return out
    with tempfile.TemporaryDirectory() as tmp:
        for py in sorted(scripts.glob("*.py")):
            rel = "scripts/" + py.name
            try:
                py_compile.compile(str(py), cfile=os.path.join(tmp, py.name + "c"), doraise=True)
            except py_compile.PyCompileError as e:
                out.append("%s: does not compile (%s)" % (rel, str(e).strip().splitlines()[-1]))
                continue
            try:
                src = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not has_cli(src) or rel in SKIP_HELP or "%s/%s" % (plugin.name, rel) in SKIP_HELP:
                continue
            env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin))
            try:
                p = subprocess.run([sys.executable, "-I", str(py.resolve()), "--help"], cwd=tmp, env=env,
                                   capture_output=True, text=True, timeout=HELP_TIMEOUT,
                                   encoding="utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                out.append("%s: --help took over %d s" % (rel, HELP_TIMEOUT))
                continue
            if p.returncode != 0:
                tail = (p.stderr.strip().splitlines() or ["no output"])[-1]
                out.append("%s: --help exit %d (%s)" % (rel, p.returncode, tail))
    return out


def front_matter(text: str) -> dict:
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    keys = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return keys
        m = re.match(r"([A-Za-z_-]+):\s*(.*)$", line)
        if m:
            keys[m.group(1)] = m.group(2).strip()
    return {}


def check_skills(plugin: Path) -> list[str]:
    out = []
    for md in sorted((plugin / "skills").glob("*/SKILL.md")):
        rel = "skills/%s/SKILL.md" % md.parent.name
        try:
            fm = front_matter(md.read_text(encoding="utf-8"))
        except OSError as e:
            out.append("%s: unreadable (%s)" % (rel, e))
            continue
        if not fm:
            out.append("%s: no front matter" % rel)
            continue
        # D128: name is optional; Claude Code uses the folder name when it is absent.
        out += ["%s: front matter has no %s" % (rel, k) for k in ("description",) if not fm.get(k)]
    return out


def smoke(plugins_dir: Path) -> dict[str, list[str]]:
    result = {}
    for plugin in sorted(p for p in plugins_dir.iterdir() if p.is_dir()):
        result[plugin.name] = (check_manifest(plugin) + check_hooks(plugin)
                               + check_scripts(plugin) + check_skills(plugin))
    return result


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent / "claude" / "plugins"
    if not root.is_dir():
        print("plugin_smoke: no plugins folder at %s" % root, file=sys.stderr)
        return 1
    result = smoke(root)
    bad = 0
    for name, fails in result.items():
        if fails:
            bad += 1
            print("%s: FAIL" % name)
            for f in fails:
                print("  - %s: %s" % (name, f))
        else:
            print("%s: ok" % name)
    print("plugin smoke: %d plugin(s), %d failed" % (len(result), bad))
    return 1 if bad or not result else 0


if __name__ == "__main__":
    sys.exit(main())
