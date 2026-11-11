#!/usr/bin/env python3
"""DL263: keep the dev-standards.yml pin in step with the installed plugins.

  python3 ci_pin.py [--project DIR]           report (writes nothing)
  python3 ci_pin.py [--project DIR] --check   report; exit 1 when the pin is stale
  python3 ci_pin.py [--project DIR] --bump    rewrite the `ref:` value of the
                                              dev-standards checkout step

It edits one working-tree file. It never commits or pushes. Standard library only.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

WORKFLOW = Path(".github/workflows/dev-standards.yml")
DOCS_JSON = Path("claude/plugins/docs/.claude-plugin/plugin.json")
# The ref line of the checkout that has `repository:` and `path: .dev-standards-tools`.
REF_RE = re.compile(r"^(?P<head>\s*ref:\s*)(?P<val>[^\s#]+)(?P<tail>.*)$")


def _git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


class Lookup:
    """Finds the marketplace checkout the plugins are installed from."""

    def __init__(self, marketplace=None):
        self.root = Path(marketplace) if marketplace else self._find()

    @staticmethod
    def _find():
        cfg = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
        try:
            known = json.loads((cfg / "plugins/known_marketplaces.json").read_text("utf-8"))
        except (OSError, ValueError):
            return None
        for entry in known.values() if isinstance(known, dict) else []:
            loc = entry.get("installLocation") if isinstance(entry, dict) else None
            if loc and (Path(loc) / DOCS_JSON).is_file():
                return Path(loc)
        return None

    def docs_version(self):
        if not self.root:
            return None
        try:
            return json.loads((self.root / DOCS_JSON).read_text("utf-8")).get("version")
        except (OSError, ValueError):
            return None

    def expected_ref(self):
        """A release tag when one exists for the version, else the checkout's HEAD."""
        ver = self.docs_version()
        if not ver:
            return None
        for tag in (f"v{ver}", f"luismc-docs-v{ver}"):
            if _git(self.root, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}"):
                return tag
        return _git(self.root, "rev-parse", "HEAD")

    def is_older(self, pin, expected):
        """True when pin is not the expected commit and not a descendant of it."""
        a = _git(self.root, "rev-parse", "-q", "--verify", f"{pin}^{{commit}}")
        b = _git(self.root, "rev-parse", "-q", "--verify", f"{expected}^{{commit}}")
        if not b:
            return False
        if not a:
            return True  # a pin the checkout does not know is older than what is installed
        if a == b:
            return False
        p = subprocess.run(["git", "-C", str(self.root), "merge-base", "--is-ancestor", b, a])
        return p.returncode != 0


def find_ref(lines):
    """Index of the ref line in the checkout step of the tools repo, or None."""
    for i, line in enumerate(lines):
        if "{{DEV_STANDARDS_REPO}}" in line or "repository:" in line:
            for j in range(i, min(i + 4, len(lines))):
                if REF_RE.match(lines[j]):
                    return j
    for j, line in enumerate(lines):
        if REF_RE.match(line):
            return j
    return None


def bump(path, new_ref):
    """Rewrite only the ref value. Returns (old, new) or None when already equal."""
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().splitlines(keepends=True)
    i = find_ref(lines)
    if i is None:
        raise ValueError("no ref: line found")
    body = lines[i].rstrip("\r\n")
    eol = lines[i][len(body):]
    m = REF_RE.match(body)
    old = m["val"]
    if old == new_ref:
        return None
    lines[i] = f"{m['head']}{new_ref}{m['tail']}{eol}"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("".join(lines))
    return old, new_ref


def run(project, mode, lookup, out=print):
    """Returns (exit code, message lines are printed through out)."""
    wf = Path(project) / WORKFLOW
    if not wf.is_file():
        out(f"CI workflow: not installed ({WORKFLOW.as_posix()} is missing)")
        return 0
    lines = wf.read_text("utf-8").splitlines()
    i = find_ref(lines)
    pin = REF_RE.match(lines[i])["val"] if i is not None else None
    if not pin:
        out("CI workflow: broken (no ref: line in dev-standards.yml)")
        return 1 if mode == "check" else 0
    if pin.startswith("{{"):
        out(f"CI workflow: broken (pin {pin} is not filled)")
        return 1 if mode == "check" else 0
    ver, expected = lookup.docs_version(), lookup.expected_ref()
    if not ver or not expected:
        out("CI pin: cannot tell, the installed plugins' marketplace checkout was not found")
        return 0
    stale = lookup.is_older(pin, expected)
    cmd = "python3 ci_pin.py --bump"
    if mode == "bump":
        if not stale:
            out(f"dev-standards.yml pin {pin} is current for luismc-docs {ver}; nothing changed")
            return 0
        res = bump(wf, expected)
        out(f"dev-standards.yml: ref {res[0]} -> {res[1]} (luismc-docs {ver}). Review and commit it yourself.")
        return 0
    if stale:
        out(f"dev-standards.yml pins {pin}, older than the installed luismc-docs {ver}; "
            f"generated docs will fail G1 in CI; run {cmd}")
        return 1 if mode == "check" else 0
    out(f"dev-standards.yml pin {pin} matches luismc-docs {ver}")
    return 0


def main(argv=None, lookup=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", default=".")
    ap.add_argument("--marketplace", help="marketplace checkout (default: found from the Claude config)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--bump", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    mode = "bump" if a.bump else "check" if a.check else "status"
    return run(a.project, mode, lookup or Lookup(a.marketplace))


if __name__ == "__main__":
    sys.exit(main())
