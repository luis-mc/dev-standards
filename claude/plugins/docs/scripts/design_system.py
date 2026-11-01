#!/usr/bin/env python3
"""design_system: the design system's folder, versions and approvals (DOCSPEC section 15).

  design_system.py init [--apply]                     create docs/design-system/ from the templates (never overwrites)
  design_system.py status                             versions, the enforced one, approvals, drift
  design_system.py check [--json]                     findings (also run by docs_check.py)
  design_system.py visuals [--version V]              rebuild review-visuals/index.html (offline gallery)
  design_system.py promote --approved-by WHO --approved-on DATE --evidence TEXT [--apply]
                                                      next-version -> the next numbered folder, only with a recorded approval
  design_system.py approve-implementation VERSION --approved-on DATE --evidence TEXT [--apply]
  design_system.py guards --stack typescript-vitest [--dest DIR] [--apply]
                                                      copy the guard-test templates for a stack
  design_system.py styles [--json]                    read-only: list the project's style files and CSS custom properties

Layout (R15.1): docs/design-system/{README.md, approvals.json, next-version/, v1/, v2/ ...}.
Every command is a dry run until --apply. Standard library only, Python 3.9 or later.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_lib as D  # noqa: E402

PLUGIN = Path(__file__).resolve().parent.parent
TEMPLATES = PLUGIN / "templates" / "design-system"
DS_REL = "docs/design-system"
DRAFT = "next-version"
NUMBERED = re.compile(r"^v([1-9]\d*)$")
VERSION_FILES = ("README.md", "ux-rules.md", "components.md", "tokens.md", "content.md", "CHANGES.md", "review-visuals/index.html")
ONE_TIME = ("audit", "visual")  # added once after approval, then frozen too (R15.5); not in the digest
STATUS_RE = re.compile(r"<!-- status:start -->.*?<!-- status:end -->", re.S)
ENTRY_RE = re.compile(r"^- C\d+\b", re.M)
ORDER_RE = re.compile(r"^#{1,6}\s*order of work\b", re.I | re.M)
RULE_ID_RE = re.compile(r"^\|\s*(UX-\d+)\s*\|", re.M)
GUARD_STACKS = {"typescript-vitest": "typescript-vitest"}
ERR, WARN = "error", "warning"


def finding(sev, code, path, msg):
    return {"severity": sev, "code": code, "path": path, "message": msg}


def today() -> str:
    return os.environ.get("DOCS_TODAY") or dt.date.today().isoformat()


# ------------------------------------------------------------------ layout
def ds_dir(root: Path) -> Path:
    return Path(root) / DS_REL


def numbers(root: Path) -> list:
    d = ds_dir(root)
    if not d.is_dir():
        return []
    return sorted(int(m.group(1)) for p in d.iterdir() if p.is_dir() and (m := NUMBERED.match(p.name)))


def enforced(root: Path) -> str | None:
    """The version apps follow: the highest numbered folder, else next-version (R15.3)."""
    n = numbers(root)
    if n:
        return f"v{n[-1]}"
    return DRAFT if (ds_dir(root) / DRAFT).is_dir() else None


def _norm(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def tree_digest(folder: Path) -> str:
    """sha256 over `relpath hash` lines of every file but the one-time audit/ and visual/ (R15.5)."""
    rels = {}
    for p in Path(folder).rglob("*"):
        if p.is_file():
            rel = p.relative_to(folder).as_posix()
            if rel.split("/")[0] not in ONE_TIME:
                rels[rel] = p
    # sorted as strings (code points), not as Paths: Windows compares Paths case-insensitively
    lines = [f"{rel} {hashlib.sha256(_norm(rels[rel].read_bytes())).hexdigest()}" for rel in sorted(rels)]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def read_approvals(root: Path) -> dict:
    p = ds_dir(root) / "approvals.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {"versions": {}}
    return {"versions": {}}


def write_approvals(root: Path, data: dict) -> None:
    (ds_dir(root) / "approvals.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _set_writable(folder: Path, writable: bool) -> None:
    for p in Path(folder).rglob("*"):
        if p.is_file():
            mode = p.stat().st_mode
            p.chmod(mode | stat.S_IWUSR if writable else mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


# ------------------------------------------------------------------ visuals
def _inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)


def _cell(c: str) -> str:
    c = c.strip()
    inner = c.strip("`")
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)|hsla?\([^)]*\)", inner):
        return f'<span class="sw" style="background:{html.escape(inner)}"></span>{_inline(c)}'
    return _inline(c)


def md_to_html(text: str) -> str:
    """A small Markdown renderer for the gallery: headings, lists, tables, code, paragraphs. No network."""
    out, lines, i = [], text.splitlines(), 0
    para: list = []

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("<!--"):
            i += 1
        elif ln.startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
        elif re.match(r"#{1,6}\s", ln):
            flush()
            lvl = len(ln) - len(ln.lstrip("#"))
            title = ln[lvl:].strip()
            out.append(f'<h{lvl} id="{re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")}">{_inline(title)}</h{lvl}>')
            i += 1
        elif ln.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c for c in lines[i].strip().strip("|").split("|")])
                i += 1
            body = [r for r in rows if not all(re.fullmatch(r"\s*:?-+:?\s*", c) for c in r)]
            if body:
                head, rest = body[0], body[1:]
                out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c.strip())}</th>" for c in head) + "</tr></thead><tbody>"
                           + "".join("<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in r) + "</tr>" for r in rest) + "</tbody></table>")
        elif re.match(r"\s*[-*]\s", ln):
            flush()
            items = []
            while i < len(lines) and re.match(r"\s*[-*]\s", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s", "", lines[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>")
        elif not ln.strip():
            flush()
            i += 1
        else:
            para.append(ln.strip())
            i += 1
    flush()
    return "\n".join(out)


GALLERY_CSS = (
    ":root{--bg:#fff;--fg:#1b1f24;--mute:#59636e;--line:#d0d7de;--code:#f2f4f6}"
    "@media(prefers-color-scheme:dark){:root{--bg:#14171a;--fg:#e6e9ec;--mute:#9aa4af;--line:#363c43;--code:#1f2429}}"
    "body{margin:0;font:16px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg)}"
    "nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:8px 16px;display:flex;gap:16px;flex-wrap:wrap}"
    "nav a{color:var(--fg)}main{max-width:960px;margin:0 auto;padding:0 16px 48px}"
    "table{border-collapse:collapse;width:100%;margin:12px 0;display:block;overflow-x:auto}"
    "th,td{border:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}"
    "code,pre{background:var(--code);border-radius:4px}code{padding:0 4px}pre{padding:8px;overflow-x:auto}"
    ".sw{display:inline-block;width:1.1em;height:1.1em;border:1px solid var(--line);vertical-align:-.2em;margin-right:6px}"
    "section{border-top:1px solid var(--line);margin-top:24px}.meta{color:var(--mute)}"
)
SECTIONS = (("README.md", "Version"), ("CHANGES.md", "Changes"), ("ux-rules.md", "Rules"), ("components.md", "Components"),
            ("tokens.md", "Tokens"), ("content.md", "Words"))


def sources_digest(folder: Path) -> str:
    h = hashlib.sha256()
    for name, _ in SECTIONS:
        p = Path(folder) / name
        h.update(_norm(p.read_bytes()) if p.is_file() else b"-")
    return h.hexdigest()[:16]


def build_visuals(folder: Path, title: str = "Design system") -> Path:
    folder = Path(folder)
    parts, nav = [], []
    for name, label in SECTIONS:
        p = folder / name
        if not p.is_file():
            continue
        sid = label.lower()
        nav.append(f'<a href="#{sid}">{label}</a>')
        parts.append(f'<section id="{sid}"><p class="meta">{html.escape(name)}</p>{md_to_html(p.read_text(encoding="utf-8"))}</section>')
    page = (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)} {html.escape(folder.name)}</title><style>{GALLERY_CSS}</style></head><body>"
            f"<!-- source-digest: {sources_digest(folder)} -->\n<nav>{''.join(nav)}</nav><main>{''.join(parts)}</main></body></html>\n")
    out = folder / "review-visuals" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


def visuals_fresh(folder: Path) -> bool:
    p = Path(folder) / "review-visuals" / "index.html"
    if not p.is_file():
        return False
    m = re.search(r"<!-- source-digest: (\w+) -->", p.read_text(encoding="utf-8"))
    return bool(m) and m.group(1) == sources_digest(folder)


# ------------------------------------------------------------------ checks
def check(root: Path, base: str | None = None) -> list:
    """Warnings about the design-system folder (R15.7). Silent in a repo that has none yet."""
    root = Path(root)
    d = ds_dir(root)
    if not d.is_dir():
        return []
    entries = [p for p in d.iterdir() if p.name != ".gitkeep"]
    if not entries:
        return []
    out = []
    rel = lambda *a: "/".join((DS_REL,) + a)  # noqa: E731
    readme = d / "README.md"
    if not readme.is_file():
        out.append(finding(WARN, "DS1", rel("README.md"), "missing: the README holds what lives here, the order of work and the promotion steps (R15.2)"))
    elif not ORDER_RE.search(readme.read_text(encoding="utf-8")):
        out.append(finding(WARN, "DS1", rel("README.md"), "no 'Order of work' section (R15.2)"))
    nums = numbers(root)
    for p in entries:
        if p.name in ("README.md", "approvals.json"):
            continue
        if not p.is_dir() or not (NUMBERED.match(p.name) or p.name == DRAFT):
            out.append(finding(WARN, "DS3", rel(p.name), "a version folder is v1, v2 ... or next-version; nothing else sits here (R15.1)"))
    for i, n in enumerate(nums):
        if n != i + 1:
            out.append(finding(WARN, "DS3", rel(f"v{n}"), "versions are numbered v1, v2 ... without a gap (R15.1)"))
    if nums and not (d / DRAFT).is_dir():
        out.append(finding(WARN, "DS3", rel(DRAFT), "missing: every change goes into next-version (R15.3)"))
    appr = read_approvals(root).get("versions", {})
    for name in [f"v{n}" for n in nums] + ([DRAFT] if (d / DRAFT).is_dir() else []):
        folder = d / name
        for f in VERSION_FILES:
            if not (folder / f).is_file():
                out.append(finding(WARN, "DS3", rel(name, f), "missing from the version folder (R15.2)"))
        rules = RULE_ID_RE.findall((folder / "ux-rules.md").read_text(encoding="utf-8")) if (folder / "ux-rules.md").is_file() else []
        for rid in sorted({r for r in rules if rules.count(r) > 1}):
            out.append(finding(WARN, "DS5", rel(name, "ux-rules.md"), f"rule ID {rid} appears twice (R15.2)"))
        if (folder / "ux-rules.md").is_file() and not visuals_fresh(folder) and name in (DRAFT, f"v{nums[-1]}" if nums else DRAFT):
            out.append(finding(WARN, "DS4", rel(name, "review-visuals/index.html"), "missing or older than the version's files: run design_system.py visuals"))
        if NUMBERED.match(name):
            rec = appr.get(name)
            if not rec or not rec.get("approved"):
                out.append(finding(WARN, "DS2", rel(name), "numbered version without a recorded owner approval in approvals.json (R15.4)"))
            elif rec.get("digest") and rec["digest"] != tree_digest(folder):
                out.append(finding(WARN, "DS2", rel(name), "edited after its approval; a numbered version is read-only, put the change into next-version (R15.5)"))
    if base and nums:
        r = D.git(root, "diff", "--no-renames", "--name-status", base, "--", *[rel(f"v{n}") + "/" for n in nums])
        if r.returncode == 0:
            for ln in r.stdout.splitlines():
                st, _, path = ln.partition("\t")
                parts = path.split("/")
                if len(parts) > 3 and parts[3] in ONE_TIME and st[:1] == "A":
                    continue
                if st[:1] != "A":
                    out.append(finding(WARN, "DS2", path, f"{st[:1]}: this branch changes a numbered version; put the change into next-version (R15.5)"))
    return out


# ------------------------------------------------------------------ styles
STYLE_NAMES = re.compile(r"(^|[-_.])(tokens?|theme|themes|variables|colors?)\.(css|scss|less|json|js|ts|mjs|cjs)$|^tailwind\.config\.\w+$|^theme\.\w+$", re.I)
SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", "coverage", "vendor", "docs", ".venv", "__pycache__"}
CSS_VAR_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;}\n]+)")
MAX_STYLE_BYTES = 200_000


def find_styles(root: Path, limit: int = 40) -> list:
    """Candidate style files and the CSS custom properties in them. Read-only; the design-system folder is skipped."""
    root = Path(root)
    found = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            p = Path(dirpath) / f
            is_css = f.endswith((".css", ".scss", ".less"))
            if not (STYLE_NAMES.search(f) or is_css):
                continue
            try:
                if p.stat().st_size > MAX_STYLE_BYTES:
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            props = [(n, v.strip()) for n, v in CSS_VAR_RE.findall(text)] if is_css else []
            if STYLE_NAMES.search(f) or props:
                found.append({"path": p.relative_to(root).as_posix(), "properties": [{"name": n, "value": v} for n, v in props[:60]]})
            if len(found) >= limit:
                return found
    return found


def cmd_styles(root: Path, as_json: bool) -> int:
    res = find_styles(root)
    if as_json:
        print(json.dumps(res, indent=2))
        return 0
    if not res:
        print("no style files found: keep the starter token values")
        return 0
    for f in res:
        print(f["path"])
        for p in f["properties"]:
            print(f"    {p['name']}: {p['value']}")
    print(f"styles: {len(res)} file(s); read-only, nothing was changed")
    return 0


# ------------------------------------------------------------------ commands
def cmd_init(root: Path, apply: bool) -> int:
    created, skipped = [], []
    for src in sorted(TEMPLATES.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(TEMPLATES)
        if rel.parts[0] == "guards":
            continue
        dest = ds_dir(root) / rel
        if dest.exists():
            skipped.append(dest.relative_to(root).as_posix())
            continue
        created.append(dest.relative_to(root).as_posix())
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            text = src.read_text(encoding="utf-8").replace("{{DATE}}", today())
            dest.write_text(text, encoding="utf-8")
    if apply:
        draft = ds_dir(root) / DRAFT
        if (draft / "ux-rules.md").is_file():
            build_visuals(draft)
        gk = ds_dir(root) / ".gitkeep"
        if gk.exists():
            gk.unlink()
    print(("created" if apply else "would create") + f" {len(created)} file(s), kept {len(skipped)} existing")
    for c in created:
        print("  +", c)
    if not apply:
        print("dry run: add --apply")
    return 0


def cmd_status(root: Path) -> int:
    e = enforced(root)
    print(f"design system: {DS_REL}")
    print(f"apps follow:   {e or '(none yet)'}")
    appr = read_approvals(root).get("versions", {})
    for n in numbers(root):
        rec = appr.get(f"v{n}", {})
        a = rec.get("approved") or {}
        im = rec.get("implementation")
        print(f"  v{n}: approved {a.get('date', 'NOT RECORDED')} by {a.get('by', '?')}; implementation "
              + (f"approved {im['date']}" if im else "not approved yet"))
    print(f"  {DRAFT}: " + ("present" if (ds_dir(root) / DRAFT).is_dir() else "missing"))
    res = check(root)
    for x in res:
        print(f"  {x['severity'].upper()} {x['code']} {x['path']}: {x['message']}")
    return 0


def _replace_status(readme: Path, block: str) -> None:
    text = readme.read_text(encoding="utf-8")
    new = f"<!-- status:start -->\n{block}\n<!-- status:end -->"
    readme.write_text(STATUS_RE.sub(lambda _m: new, text) if STATUS_RE.search(text) else new + "\n\n" + text, encoding="utf-8")


def _move(root: Path, src: Path, dest: Path) -> None:
    r = D.git(root, "mv", str(src), str(dest))
    if r.returncode != 0:
        shutil.move(str(src), str(dest))


def cmd_promote(root: Path, a) -> int:
    d = ds_dir(root)
    draft = d / DRAFT
    problems = []
    if not draft.is_dir():
        problems.append("next-version/ does not exist")
    if not (a.approved_by or "").strip() or not (a.evidence or "").strip() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.approved_on or ""):
        problems.append("a promotion needs the recorded owner approval: --approved-by, --approved-on YYYY-MM-DD and --evidence (where it was given)")
    if draft.is_dir():
        for f in VERSION_FILES[:-1]:
            if not (draft / f).is_file():
                problems.append(f"next-version/{f} is missing")
        ch = draft / "CHANGES.md"
        if not ch.is_file() or not ENTRY_RE.search(ch.read_text(encoding="utf-8")):
            problems.append("next-version/CHANGES.md has no entry ('- C1: ...'): nothing to promote")
    if problems:
        for p in problems:
            print("refused:", p, file=sys.stderr)
        return 2
    n = (numbers(root) or [0])[-1] + 1
    name = f"v{n}"
    print(f"{'promote' if a.apply else 'would promote'}: next-version -> {name} (approved by {a.approved_by} on {a.approved_on}: {a.evidence}); "
          f"older versions stay read-only; next-version is recreated as a copy of {name}")
    if not a.apply:
        print("dry run: add --apply")
        return 0
    _move(root, draft, d / name)
    folder = d / name
    _replace_status(folder / "README.md", f"**Status:** approved. Approved by {a.approved_by} on {a.approved_on}: {a.evidence}.")
    build_visuals(folder)
    appr = read_approvals(root)
    appr.setdefault("versions", {})[name] = {
        "approved": {"by": a.approved_by, "date": a.approved_on, "evidence": a.evidence},
        "implementation": None,
        "digest": tree_digest(folder),
    }
    write_approvals(root, appr)
    shutil.copytree(folder, draft, ignore=shutil.ignore_patterns(*ONE_TIME))
    _set_writable(draft, True)
    _replace_status(draft / "README.md", f"**Status:** draft. Not approved. Created on {today()} as a full copy of `{name}`; the apps follow `{name}` until the owner approves this draft.")
    (draft / "CHANGES.md").write_text("# Changes from " + name + "\n\nOne entry per change, `- C<n>: what changed (file; source)`.\n\n", encoding="utf-8")
    build_visuals(draft)
    _set_writable(folder, False)
    print(f"done: {name} approved and read-only; next-version recreated. Next: an audit of what each app must change, then the owner approves the implementation (approve-implementation).")
    return 0


def cmd_approve_impl(root: Path, a) -> int:
    appr = read_approvals(root)
    rec = appr.get("versions", {}).get(a.version)
    if not rec or not rec.get("approved"):
        print(f"refused: {a.version} has no recorded approval", file=sys.stderr)
        return 2
    if not a.evidence or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.approved_on or ""):
        print("refused: --approved-on YYYY-MM-DD and --evidence are required", file=sys.stderr)
        return 2
    print(f"{'recorded' if a.apply else 'would record'}: implementation of {a.version} approved on {a.approved_on}: {a.evidence}")
    if a.apply:
        rec["implementation"] = {"date": a.approved_on, "evidence": a.evidence}
        write_approvals(root, appr)
    else:
        print("dry run: add --apply")
    return 0


def cmd_guards(root: Path, a) -> int:
    src = TEMPLATES / "guards" / GUARD_STACKS[a.stack]
    dest = root / a.dest
    n = 0
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        target = dest / f.relative_to(src)
        if target.exists():
            print("  kept   ", target.relative_to(root).as_posix())
            continue
        n += 1
        print(("  write  " if a.apply else "  would  "), target.relative_to(root).as_posix())
        if a.apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, target)
    if not a.apply:
        print("dry run: add --apply")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["init", "status", "check", "visuals", "promote", "approve-implementation", "guards", "styles"])
    ap.add_argument("version", nargs="?")
    ap.add_argument("--root", default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--approved-by")
    ap.add_argument("--approved-on")
    ap.add_argument("--evidence")
    ap.add_argument("--stack", default="typescript-vitest", choices=sorted(GUARD_STACKS))
    ap.add_argument("--dest", default="scripts/design")
    ap.add_argument("--base", default=None)
    a = ap.parse_args(argv)
    root = D.repo_root(a.root)
    if a.command == "init":
        return cmd_init(root, a.apply)
    if a.command == "status":
        return cmd_status(root)
    if a.command == "styles":
        return cmd_styles(root, a.json)
    if a.command == "check":
        res = check(root, a.base)
        if a.json:
            print(json.dumps(res, indent=2))
        else:
            for x in res:
                print(f"{x['severity'].upper():7} {x['code']} {x['path']}: {x['message']}")
            print(f"design_system: {len(res)} finding(s)")
        return 1 if any(x["severity"] == ERR for x in res) else 0
    if a.command == "visuals":
        v = a.version or enforced(root)
        if not v or not (ds_dir(root) / v).is_dir():
            print("no such version folder", file=sys.stderr)
            return 2
        if NUMBERED.match(v):
            print("refused: a numbered version is read-only; rebuild next-version", file=sys.stderr)
            return 2
        print(build_visuals(ds_dir(root) / v).relative_to(root).as_posix())
        return 0
    if a.command == "promote":
        return cmd_promote(root, a)
    if a.command == "approve-implementation":
        a.version = a.version or ""
        return cmd_approve_impl(root, a)
    return cmd_guards(root, a)


if __name__ == "__main__":
    sys.exit(main())
