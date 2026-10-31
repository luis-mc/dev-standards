#!/usr/bin/env python3
"""Shared helpers for the luismc-docs scripts (DOCSPEC). Standard library only.

Front matter, the project config (docs/docs.json), the list of docs, glob
matching for the code-to-doc map, link parsing and small git helpers. Every
other script imports this one.
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

CONFIG_REL = "docs/docs.json"
DEFAULTS = {
    "schema": 1,
    "docspec": "1.0.0",
    "apps": [],
    "topics": [],
    "record_dir": "docs/project",
    "default_branch": "main",
    "stale_days": 90,
    "binding": ["docs/features", "docs/architecture", "docs/design-system"],
    "generated_reference": [],
}
STATUSES = ("proposed", "building", "live", "retired")
TYPES = ("tutorial", "how-to", "reference", "explanation")
FRONT_REQUIRED = ("id", "title", "apps", "topics", "status", "version", "owner", "type", "code")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
GENERATED = (
    "docs/index.html",
    "docs/llms.txt",
    "docs/features/index.md",
    "docs/architecture/decisions.md",
    "docs/docs-map.json",
)
SKIP_DIRS = {"_site", "node_modules", ".git"}


# --------------------------------------------------------------- front matter
def _scalar(v: str):
    v = v.strip()
    if v == "":
        return ""
    if v[0] in "\"'" and v[-1] == v[0] and len(v) >= 2:
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_scalar(x) for x in _split_list(inner)]
    if v in ("true", "false"):
        return v == "true"
    return v


def _split_list(s: str) -> list[str]:
    out, cur, q = [], "", ""
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = ""
        elif ch in "\"'":
            q = ch
            cur += ch
        elif ch == ",":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def _strip_comment(line: str) -> str:
    q = ""
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = ""
        elif ch in "\"'":
            q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def parse_front_matter(text: str):
    """Return (data, body, ok). ok is False when a `---` block is absent or unclosed."""
    if not text.startswith("---"):
        return {}, text, False
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return {}, text, False
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text, False
    data: dict = {}
    for raw in lines[1:end]:
        line = _strip_comment(raw)
        if not line.strip() or ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = _scalar(v)
    return data, "\n".join(lines[end + 1:]), True


def format_value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def set_front_matter(text: str, updates: dict, order: tuple = FRONT_REQUIRED) -> str:
    """Set keys in the front matter (create the block when absent); keeps other lines."""
    data, body, ok = parse_front_matter(text)
    if not ok:
        lines = [f"{k}: {format_value(v)}" for k, v in updates.items()]
        return "---\n" + "\n".join(lines) + "\n---\n" + text
    raw = text.split("\n")
    end = next(i for i in range(1, len(raw)) if raw[i].strip() == "---")
    block = raw[1:end]
    for k, v in updates.items():
        new = f"{k}: {format_value(v)}"
        for i, line in enumerate(block):
            if re.match(rf"^{re.escape(k)}\s*:", line):
                comment = ""
                m = re.search(r"\s+#\s.*$", line)
                if m:
                    comment = m.group(0)
                block[i] = new + comment
                break
        else:
            block.append(new)
    return "\n".join(["---"] + block + ["---"] + raw[end + 1:])


# ------------------------------------------------------------------ config
def repo_root(start: str | Path | None = None) -> Path:
    p = Path(start or os.getcwd()).resolve()
    for d in [p, *p.parents]:
        if (d / ".git").exists():
            return d
    return p


def load_config(root: Path) -> dict:
    cfg = dict(DEFAULTS)
    f = root / CONFIG_REL
    if f.is_file():
        try:
            cfg.update(json.loads(f.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    return cfg


def has_config(root: Path) -> bool:
    return (root / CONFIG_REL).is_file()


# -------------------------------------------------------------------- files
def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def posix(p) -> str:
    return str(p).replace("\\", "/")


def iter_files(root: Path, base: str = "docs", exts: tuple = (".md",)):
    top = root / base
    if not top.is_dir():
        return
    for d, dirs, files in os.walk(top):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for f in sorted(files):
            if f.endswith(exts):
                yield Path(d) / f


def lasting_docs(root: Path):
    """Markdown docs that belong to the lasting set: not branch-only work, not generated
    pages in _site, not change notes."""
    for p in iter_files(root):
        rel = posix(p.relative_to(root))
        if rel.startswith("docs/work/"):
            continue
        if "/changes/" in rel:
            continue
        yield p


def is_generated(rel: str) -> bool:
    return rel in GENERATED


def is_binding(rel: str, cfg: dict) -> bool:
    return any(rel == b or rel.startswith(b.rstrip("/") + "/") for b in cfg["binding"]) and not rel.endswith("/README.md") and not rel.endswith("/index.md") and not rel.endswith("decisions.md") and "/decisions/" not in rel and "/archive/" not in rel


def feature_dirs(root: Path):
    top = root / "docs/features"
    if top.is_dir():
        for d in sorted(top.iterdir()):
            if d.is_dir() and d.name not in ("changes",):
                yield d


# --------------------------------------------------------------------- globs
def glob_to_regex(g: str) -> re.Pattern:
    g = g.strip().replace("\\", "/")
    i, out = 0, ""
    while i < len(g):
        c = g[i]
        if c == "*":
            if g[i:i + 3] == "**/":
                out += "(?:.*/)?"
                i += 3
                continue
            if g[i:i + 2] == "**":
                out += ".*"
                i += 2
                continue
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        else:
            out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$")


def match_any(path: str, globs) -> bool:
    return any(glob_to_regex(g).match(path) for g in globs)


# --------------------------------------------------------------------- links
LINK_RE = re.compile(r"(?<!\!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMG_RE = re.compile(r"\!\[([^\]\n]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HREF_RE = re.compile(r"""(?:href|src)=["']([^"']+)["']""")


def is_external(t: str) -> bool:
    return bool(re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*:|//|#)", t))


def split_target(t: str):
    """('path', '#frag' or '')"""
    m = re.match(r"^([^#?]*)([?#].*)?$", t)
    return (m.group(1), m.group(2) or "") if m else (t, "")


def strip_code(text: str) -> str:
    """Blank out fenced code and inline code so links in examples are not read."""
    text = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r"~~~.*?~~~", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def heading_slug(h: str) -> str:
    h = re.sub(r"[`*_]", "", h.strip().lower())
    h = re.sub(r"[^\w\s-]", "", h)
    return re.sub(r"\s+", "-", h)


def anchors(text: str) -> set[str]:
    out, seen = set(), {}
    for line in strip_code(text).split("\n"):
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m:
            s = heading_slug(m.group(1))
            n = seen.get(s, 0)
            seen[s] = n + 1
            out.add(s if n == 0 else f"{s}-{n}")
    return out


def relpath(target: str, from_dir: str) -> str:
    r = os.path.relpath(target, from_dir or ".").replace("\\", "/")
    return r


# ----------------------------------------------------------------------- git
def git(root: Path, *args, check=False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=check)


def is_git(root: Path) -> bool:
    return git(root, "rev-parse", "--git-dir").returncode == 0


def tracked(root: Path, rel: str) -> bool:
    return git(root, "ls-files", "--error-unmatch", "--", rel).returncode == 0


def changed_files(root: Path, base: str | None) -> list[str]:
    """Files changed on this branch since `base` (merge-base) plus uncommitted ones."""
    files: set[str] = set()
    if base:
        mb = git(root, "merge-base", base, "HEAD")
        ref = mb.stdout.strip() if mb.returncode == 0 and mb.stdout.strip() else base
        r = git(root, "diff", "--name-only", "--diff-filter=ACMRD", ref, "HEAD")
        files.update(x for x in r.stdout.split("\n") if x)
    r = git(root, "status", "--porcelain")
    for line in r.stdout.split("\n"):
        if len(line) > 3:
            name = line[3:]
            if " -> " in name:
                name = name.split(" -> ")[1]
            files.add(name.strip('"'))
    return sorted(files)


def added_files(root: Path, base: str) -> list[str]:
    mb = git(root, "merge-base", base, "HEAD")
    ref = mb.stdout.strip() if mb.returncode == 0 and mb.stdout.strip() else base
    r = git(root, "diff", "--name-only", "--diff-filter=A", ref, "HEAD")
    return [x for x in r.stdout.split("\n") if x]


def default_base(root: Path, cfg: dict) -> str | None:
    for cand in (f"origin/{cfg['default_branch']}", cfg["default_branch"]):
        if git(root, "rev-parse", "--verify", "-q", cand).returncode == 0:
            return cand
    return None


def commit_messages(root: Path, base: str | None) -> str:
    if not base:
        return ""
    r = git(root, "log", "--format=%B", f"{base}..HEAD")
    return r.stdout if r.returncode == 0 else ""


def today() -> str:
    return os.environ.get("DOCS_TODAY") or dt.date.today().isoformat()


def parse_date(s) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(s).strip())
    except ValueError:
        return None


def first_h1(body: str, default: str = "") -> str:
    for line in strip_code(body).split("\n"):
        m = re.match(r"^#\s+(.*)$", line)
        if m:
            return m.group(1).strip()
    return default


def sections(body: str):
    """[(level, title, text)] split at ATX headings outside code."""
    out, cur, fence = [], None, False
    for line in body.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        m = None if fence else re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            if cur:
                out.append(cur)
            cur = [len(m.group(1)), m.group(2), []]
        elif cur:
            cur[2].append(line)
    if cur:
        out.append(cur)
    return [(a, b, "\n".join(c)) for a, b, c in out]
