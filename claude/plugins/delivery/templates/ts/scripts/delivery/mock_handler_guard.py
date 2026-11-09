#!/usr/bin/env python3
"""DL146: a client API function the branch adds needs a default handler in the shared e2e mock.

    mock_handler_guard.py [--base-ref REF] [--root DIR]

Looks only at what the branch adds since its base (git diff REF...HEAD). For each new
exported function in an API client file that calls a route written as a string literal
('/api/items', "/api/items", `/api/items/${id}`), it checks that a shared mock file has a
handler for that route (http.get('/api/items', ...) or rest.post(...), MSW style). A miss
fails with the route, the client function and the file to add the handler to.

Settings, optional, in .delivery/config.json:
    "e2e_mock": {"client": [globs], "mock": [globs]}
Globs match repository paths; ** matches any folders. Defaults:
    client: **/api/client.ts, **/api-client.ts, **/lib/api.ts
    mock:   **/mocks/handlers.ts, **/mocks/handlers/*.ts
No client or no mock file found: pass with a one-line note.

Limits: only string-literal paths are seen. A path built in code, a base URL in a variable
that is not at the start, or a handler made in a loop is not seen. The method is compared
only when both sides show one. Standard library only. Exit: 0 ok, 1 missing handler, 2 usage.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_CLIENT = ["**/api/client.ts", "**/api-client.ts", "**/lib/api.ts"]
DEFAULT_MOCK = ["**/mocks/handlers.ts", "**/mocks/handlers/*.ts"]

EXPORT_RE = re.compile(r"^\s*export\s+(?:async\s+)?(?:function\s*\*?\s*(\w+)|const\s+(\w+)\s*(?::[^=]+)?=)")
LITERAL_RE = re.compile(r"""(['"`])(/[^'"`\s]*)\1""")
METHOD_RE = re.compile(r"""method\s*:\s*['"`](\w+)['"`]|\.(get|post|put|patch|delete)\s*[<(]""", re.I)
HANDLER_RE = re.compile(r"""\b(?:http|rest)\.(get|post|put|patch|delete|all|head|options)\s*\(\s*(['"`])(.*?)\2""", re.I | re.S)


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), done.stderr.strip()))
    return done.stdout


def glob_re(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile("^" + out + "$")


def match_files(files: list[str], globs: list[str]) -> list[str]:
    regs = [glob_re(g) for g in globs]
    return [f for f in files if any(r.match(f) for r in regs)]


def norm_path(p: str) -> str:
    """A route in one shape: no query, no trailing slash, every parameter becomes *."""
    p = p.split("?")[0]
    p = re.sub(r"\$\{[^}]*\}|:\w+|\{\w+\}", "*", p)
    return p.rstrip("/") or "/"


def added_names(diff: str) -> set[str]:
    names = set()
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            m = EXPORT_RE.match(line[1:])
            if m:
                names.add(m.group(1) or m.group(2))
    return names


def functions(text: str, names: set[str]) -> list[tuple[str, str]]:
    """(name, body) for each exported function in names; a body runs to the next export."""
    lines = text.splitlines()
    starts = []
    for i, line in enumerate(lines):
        m = EXPORT_RE.match(line)
        if m:
            starts.append((i, m.group(1) or m.group(2)))
    out = []
    for n, (i, name) in enumerate(starts):
        if name in names:
            end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
            out.append((name, "\n".join(lines[i:end])))
    return out


def routes_of(body: str) -> list[tuple[str, str | None]]:
    """(path, method or None) for each route literal in a function body."""
    m = METHOD_RE.search(body)
    method = (m.group(1) or m.group(2)).lower() if m else None
    found = []
    for lit in LITERAL_RE.finditer(body):
        path = lit.group(2)
        # a leading ${BASE}/api/x is read after the base; a literal like '/' alone is no route
        if len(path) > 1:
            found.append((path, method))
    # a template starting with ${BASE} has no leading '/': read its first '/...' part
    for lit in re.finditer(r"`\$\{[^}]*\}(/[^`\s]*)`", body):
        found.append((lit.group(1), method))
    return found


def handlers_of(text: str) -> list[tuple[str, str]]:
    return [(m.group(1).lower(), norm_path(m.group(3))) for m in HANDLER_RE.finditer(text)]


def has_handler(handlers: list[tuple[str, str]], path: str, method: str | None) -> bool:
    want = norm_path(path)
    for hm, hp in handlers:
        # a handler may carry a host or a '*' prefix: compare the tail
        if hp == want or hp.endswith(want if want.startswith("/") else "/" + want):
            if method is None or hm in (method, "all"):
                return True
    return False


def check(root: Path, base: str) -> int:
    cfg = {}
    cfgf = root / ".delivery" / "config.json"
    if cfgf.is_file():
        try:
            cfg = json.loads(cfgf.read_text(encoding="utf-8")).get("e2e_mock") or {}
        except (OSError, ValueError):
            print("mock_handler_guard: .delivery/config.json is not readable JSON", file=sys.stderr)
            return 2
    client_globs = cfg.get("client") or DEFAULT_CLIENT
    mock_globs = cfg.get("mock") or DEFAULT_MOCK
    tracked = [f for f in git(root, "ls-files").splitlines() if f]
    clients = match_files(tracked, client_globs)
    mocks = match_files(tracked, mock_globs)
    if not clients or not mocks:
        print("mock_handler_guard: ok (no API client or no shared e2e mock found; set e2e_mock in .delivery/config.json to check)")
        return 0
    handlers: list[tuple[str, str]] = []
    for m in mocks:
        handlers += handlers_of((root / m).read_text(encoding="utf-8", errors="replace"))
    target = mocks[0]
    missing = []
    for c in clients:
        diff = git(root, "diff", "-U0", "%s...HEAD" % base, "--", c)
        names = added_names(diff)
        if not names:
            continue
        text = (root / c).read_text(encoding="utf-8", errors="replace")
        for name, body in functions(text, names):
            for path, method in routes_of(body):
                if not has_handler(handlers, path, method):
                    missing.append((path, method, name, c))
    if not missing:
        print("mock_handler_guard: ok")
        return 0
    for path, method, name, c in missing:
        print("mock_handler_guard: FAIL: route %s%s, client function %s (%s), has no default handler in the shared e2e mock. "
              "Add one to %s." % ((method.upper() + " ") if method else "", path, name, c, target), file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail when an added client API function has no default e2e mock handler.")
    ap.add_argument("--base-ref", "--base", dest="base", default="origin/main", help="base to diff against (default origin/main)")
    ap.add_argument("--root", default=".", help="repository root (default: current folder)")
    args = ap.parse_args()
    try:
        return check(Path(args.root).resolve(), args.base)
    except RuntimeError as exc:
        print("mock_handler_guard: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
