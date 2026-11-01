#!/usr/bin/env python3
"""docs_index: build the browsable docs (D2) and the generated files (DOCSPEC section 6).

  docs_index.py build [--root R] [--mermaid PATH]   write everything
  docs_index.py check [--root R]                    exit 1 when a committed generated file is stale
  docs_index.py fetch-mermaid [--root R]            download the pinned mermaid.js into docs/_site/vendor/ (override of the committed copy)

Writes (never edit by hand):
  docs/features/index.md        features by app, by topic, by status, and gaps
  docs/architecture/decisions.md  every decision: feature and cross-cutting
  docs/docs-map.json            code globs -> docs (read by docs_check map)
  docs/llms.txt                 a map of the docs for agents
  docs/_site/**                 one HTML page per doc, search data, vendored mermaid.js (git-ignored)
  docs/index.html               the home page: search, feature index by app and topic, gaps; opens from file://

The renderer is a small Markdown subset (headings, paragraphs, lists, tables, fenced code,
blockquotes, links, images, emphasis). Mermaid blocks are drawn when a mermaid.js is vendored
(by default the plugin's committed vendor/mermaid.min.js, Mermaid 11.4.1; overrides: --mermaid PATH, env
DOCS_MERMAID_JS, fetch-mermaid); if no copy is found they show as readable source. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_lib as D  # noqa: E402

PLUGIN = Path(__file__).resolve().parent.parent
MERMAID_VERSION = "11.4.1"
# SHA-256 of dist/mermaid.min.js at MERMAID_VERSION; fetch-mermaid refuses any other bytes.
MERMAID_SHA256 = "a43bc1afd446f9c4cc66ac5dd45d02e8d65e26fc5344ec0ef787f88d6ddb6f9e"
MERMAID_URL = f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"

CSS = """
:root{--bg:#fff;--fg:#1c1f23;--muted:#5b6470;--line:#d9dde3;--accent:#1d5fd1;--code:#f3f5f8;--warn:#9a5b00}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#14171b;--fg:#e6e9ee;--muted:#9aa4b2;--line:#2b313a;--accent:#7aa7ff;--code:#1d2128;--warn:#f0b35a}}
:root[data-theme=dark]{--bg:#14171b;--fg:#e6e9ee;--muted:#9aa4b2;--line:#2b313a;--accent:#7aa7ff;--code:#1d2128;--warn:#f0b35a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:920px;margin:0 auto;padding:16px}header.top{border-bottom:1px solid var(--line);padding:8px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
a{color:var(--accent)}h1,h2,h3{line-height:1.25}code,pre{background:var(--code);border-radius:4px;font:14px ui-monospace,Consolas,monospace}code{padding:1px 4px}pre{padding:12px;overflow:auto}
table{border-collapse:collapse;display:block;overflow:auto;max-width:100%}th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
blockquote{border-left:3px solid var(--line);margin:0;padding:0 12px;color:var(--muted)}img{max-width:100%}.muted{color:var(--muted)}.stale,.gap{color:var(--warn)}
input[type=search]{width:100%;padding:8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);font:inherit}
.meta{color:var(--muted);font-size:14px}ul.hits{list-style:none;padding:0}ul.hits li{margin:6px 0}.mermaid{text-align:center}
"""


# ------------------------------------------------------------- markdown
def inline(s: str, link_fix) -> str:
    s = html.escape(s, quote=False)
    codes = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", keep, s)
    s = re.sub(r"\!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;[^)]*&quot;)?\)",
               lambda m: f'<img alt="{m.group(1)}" src="{html.escape(link_fix(html.unescape(m.group(2))), quote=True)}">', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^)]*&quot;)?\)",
               lambda m: f'<a href="{html.escape(link_fix(html.unescape(m.group(2))), quote=True)}">{m.group(1)}</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", s)
    return s


def render_markdown(text: str, link_fix=lambda t: t) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i, para = 0, []

    def flush():
        if para:
            out.append("<p>" + inline(" ".join(para), link_fix) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(```|~~~)\s*([\w-]*)\s*$", line)
        if m:
            flush()
            fence, lang = m.group(1), m.group(2)
            buf = []
            i += 1
            while i < len(lines) and not lines[i].startswith(fence):
                buf.append(lines[i])
                i += 1
            i += 1
            code = html.escape("\n".join(buf), quote=False)
            if lang == "mermaid":
                out.append(f'<pre class="mermaid">{code}</pre>')
            else:
                out.append(f'<pre><code class="lang-{lang}">{code}</code></pre>')
            continue
        h = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if h:
            flush()
            n = len(h.group(1))
            out.append(f'<h{n} id="{D.heading_slug(h.group(2))}">{inline(h.group(2), link_fix)}</h{n}>')
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if line.startswith(">"):
            flush()
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + render_markdown("\n".join(buf), link_fix) + "</blockquote>")
            continue
        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", lines[i + 1]):
            flush()
            def cells(r):
                r = r.strip()
                if r.startswith("|"):
                    r = r[1:]
                if r.endswith("|"):
                    r = r[:-1]
                return [c.strip() for c in re.split(r"(?<!\\)\|", r)]
            head = cells(line)
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(cells(lines[i]))
                i += 1
            t = "<table><thead><tr>" + "".join(f"<th>{inline(c, link_fix)}</th>" for c in head) + "</tr></thead><tbody>"
            for r in rows:
                t += "<tr>" + "".join(f"<td>{inline(c, link_fix).replace('&lt;br&gt;', '<br>')}</td>" for c in r) + "</tr>"
            out.append(t + "</tbody></table>")
            continue
        lm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if lm:
            flush()
            ordered = lm.group(2)[0].isdigit()
            items = []
            while i < len(lines):
                lm2 = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
                if lm2:
                    items.append(lm2.group(3))
                    i += 1
                elif lines[i].startswith("  ") and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip()
                    i += 1
                else:
                    break
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x, link_fix)}</li>" for x in items) + f"</{tag}>")
            continue
        if not line.strip():
            flush()
        else:
            para.append(line.strip())
        i += 1
    flush()
    return "\n".join(out)


# ------------------------------------------------------------ collecting
def collect(root: Path, cfg: dict) -> dict:
    """Read every lasting doc: path, front matter, title, text for search."""
    docs = []
    for p in D.lasting_docs(root):
        rel = D.posix(p.relative_to(root))
        if rel in D.GENERATED:
            continue
        text = D.read(p)
        fm, body, ok = D.parse_front_matter(text)
        docs.append({
            "path": rel, "fm": fm, "has_fm": ok, "body": body,
            "title": fm.get("title") or D.first_h1(body, Path(rel).stem),
        })
    features, gaps = [], []
    for fd in D.feature_dirs(root):
        spec = fd / "spec.md"
        rel = D.posix(fd.relative_to(root))
        if not spec.is_file():
            gaps.append(f"{rel}/: feature folder with no spec.md")
            continue
        text = D.read(spec)
        fm, body, ok = D.parse_front_matter(text)
        if not ok:
            gaps.append(f"{rel}/spec.md: no front matter")
        f = {
            "id": fm.get("id") or fd.name,
            "title": fm.get("title") or D.first_h1(body, fd.name),
            "apps": fm.get("apps") if isinstance(fm.get("apps"), list) else [],
            "topics": fm.get("topics") if isinstance(fm.get("topics"), list) else [],
            "status": fm.get("status") or "",
            "version": fm.get("version") or "",
            "last_verified": str(fm.get("last_verified") or ""),
            "code": fm.get("code") if isinstance(fm.get("code"), list) else [],
            "path": D.posix(spec.relative_to(root)),
            "dir": fd.name,
        }
        f["stale"] = is_stale(f["last_verified"], cfg["stale_days"])
        if ok and not f["apps"]:
            gaps.append(f"{f['path']}: no apps in front matter")
        if ok and not f["topics"]:
            gaps.append(f"{f['path']}: no topics in front matter")
        if "```mermaid" not in body and not D.IMG_RE.search(body):
            gaps.append(f"{f['path']}: no diagram or image")
        if not str(fm.get("owner") or "").strip():
            gaps.append(f"{f['path']}: no owner")
        features.append(f)
    for app in cfg.get("apps", []):
        if not any(app in f["apps"] for f in features):
            gaps.append(f"app {app}: no feature spec lists it")
    for n in ("README.md", "apps.md", "system.md", "glossary.md", "quality.md"):
        if not (root / "docs/overview" / n).is_file():
            gaps.append(f"docs/overview/{n}: missing")
    return {"docs": docs, "features": features, "gaps": gaps}


def is_stale(last_verified: str, days: int) -> bool:
    d = D.parse_date(last_verified)
    if d is None:
        return True
    import datetime as dt
    return (dt.date.fromisoformat(D.today()) - d).days > int(days)


# ---------------------------------------------------------- generated files
def feature_index_md(c: dict, cfg: dict) -> str:
    feats = sorted(c["features"], key=lambda f: (f["title"].lower()))
    out = ["<!-- generated by luismc-docs docs_index.py; do not edit -->", "# Features", ""]

    def rows(items, key=None):
        r = ["| Feature | Apps | Topics | Status | Version | Last verified |", "|---|---|---|---|---|---|"]
        for f in items:
            lv = f["last_verified"] or "never"
            r.append(f"| [{f['title']}]({f['dir']}/spec.md) | {', '.join(f['apps'])} | {', '.join(f['topics'])} | {f['status']} | {f['version']} | {lv} |")
        return r

    out += ["## By app", ""]
    apps = sorted({a for f in feats for a in f["apps"]} | set(cfg.get("apps", [])))
    for a in apps:
        items = [f for f in feats if a in f["apps"]]
        out += [f"### {a}", ""]
        out += rows(items) if items else ["No feature lists this app yet."]
        out.append("")
    out += ["## By topic", ""]
    topics = sorted({t for f in feats for t in f["topics"]} | set(cfg.get("topics", [])))
    for t in topics:
        items = [f for f in feats if t in f["topics"]]
        out += [f"### {t}", ""]
        out += rows(items) if items else ["No feature lists this topic yet."]
        out.append("")
    out += ["## By status", ""]
    for s in D.STATUSES:
        items = [f for f in feats if f["status"] == s]
        if items:
            out += [f"### {s}", ""] + rows(items) + [""]
    odd = [f for f in feats if f["status"] not in D.STATUSES]
    if odd:
        out += ["### unset or unknown", ""] + rows(odd) + [""]
    out += ["## Gaps", ""]
    out += [f"- {g}" for g in c["gaps"]] if c["gaps"] else ["None."]
    return "\n".join(out).rstrip() + "\n"


def collect_decisions(root: Path, cfg: dict) -> list[dict]:
    out = []
    d = root / "docs/architecture/decisions"
    if d.is_dir():
        for p in sorted(d.glob("*.md")):
            fm, body, ok = D.parse_front_matter(D.read(p))
            if p.name.lower() == "readme.md":
                continue
            out.append({"scope": "cross-cutting", "id": fm.get("id") or p.stem, "title": fm.get("title") or D.first_h1(body, p.stem),
                        "status": fm.get("status") or "", "date": str(fm.get("date") or ""),
                        "chosen": "", "link": D.posix(os.path.relpath(p, root / "docs/architecture"))})
    rec = root / cfg["record_dir"] / "content"
    if rec.is_dir():
        for p in sorted(rec.rglob("decisions.json")):
            try:
                data = json.loads(D.read(p))
            except ValueError:
                continue
            feature = p.parent.name
            for x in data.get("decisions", []):
                if x.get("status") != "decided":
                    continue
                out.append({"scope": feature, "id": x.get("id", ""), "title": x.get("question", ""), "status": "decided",
                            "date": str(x.get("decided", "")), "chosen": x.get("chosen", ""), "link": ""})
    for f in D.feature_dirs(root):
        spec = f / "spec.md"
        if not spec.is_file():
            continue
        for title, _lvl in ():
            pass
        for lvl, title, text in D.sections(D.read(spec)):
            if re.match(r"^(\d+\.\s*)?Decisions\s*$", title):
                for line in text.split("\n"):
                    cells = [x.strip() for x in line.strip().strip("|").split("|")]
                    if len(cells) >= 3 and re.match(r"^D\d+", cells[0]):
                        out.append({"scope": f.name, "id": cells[0], "title": cells[1], "status": "decided",
                                    "date": cells[3] if len(cells) > 3 else "", "chosen": cells[2],
                                    "link": D.posix(os.path.relpath(spec, root / "docs/architecture"))})
    return out


def decisions_md(decs: list[dict]) -> str:
    out = ["<!-- generated by luismc-docs docs_index.py; do not edit -->", "# Decisions", "",
           "Feature decisions come from each feature's `decisions.json` (and the Decisions table of its spec); cross-cutting decisions are the records in `decisions/`.", "",
           "| Scope | ID | Decision | Chosen | Status | Date |", "|---|---|---|---|---|---|"]
    seen = set()
    for d in sorted(decs, key=lambda x: (x["scope"] != "cross-cutting", x["scope"], x["id"])):
        key = (d["scope"], d["id"])
        if key in seen:
            continue
        seen.add(key)
        title = f"[{d['title']}]({d['link']})" if d["link"] else d["title"]
        out.append(f"| {d['scope']} | {d['id']} | {title} | {d['chosen']} | {d['status']} | {d['date']} |")
    return "\n".join(out) + "\n"


def docs_map(c: dict) -> dict:
    m = {}
    for f in c["features"]:
        for g in f["code"]:
            m.setdefault(g, [])
            if f["path"] not in m[g]:
                m[g].append(f["path"])
    for d in c["docs"]:
        if d["path"].startswith("docs/features/"):
            continue
        code = d["fm"].get("code")
        if isinstance(code, list):
            for g in code:
                m.setdefault(g, [])
                if d["path"] not in m[g]:
                    m[g].append(d["path"])
    return {"schema": 1, "map": {k: sorted(v) for k, v in sorted(m.items())}}


def llms_txt(c: dict, cfg: dict) -> str:
    out = ["# Documentation map", "", "> Generated by luismc-docs. Read docs/README.md first; the rules are DOCSPEC.", ""]
    groups = {}
    for d in c["docs"]:
        top = d["path"].split("/")[1] if d["path"].count("/") >= 2 else "docs"
        groups.setdefault(top, []).append(d)
    for g in sorted(groups):
        out += [f"## {g}", ""]
        for d in sorted(groups[g], key=lambda x: x["path"]):
            out.append(f"- [{d['title']}]({d['path']})")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ----------------------------------------------------------------- site
def page(title: str, body: str, home_href: str, extra_head: str = "", nav: str = "") -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{CSS}</style>{extra_head}</head><body>"
            f'<header class="top"><a href="{home_href}">Docs home</a>{nav}</header><main>{body}</main></body></html>')


PLUGIN_MERMAID = PLUGIN / "vendor/mermaid.min.js"  # the committed copy (MIT, see vendor/README.md)


def mermaid_js(root: Path, explicit: str | None) -> Path | None:
    for cand in (explicit, os.environ.get("DOCS_MERMAID_JS"), str(root / "docs/_site/vendor/mermaid.min.js"), str(PLUGIN_MERMAID)):
        if cand and Path(cand).is_file():
            return Path(cand)
    return None


def build_site(root: Path, cfg: dict, c: dict, mermaid: str | None) -> list[str]:
    site = root / "docs/_site"
    keep_vendor = None
    if (site / "vendor/mermaid.min.js").is_file():
        keep_vendor = (site / "vendor/mermaid.min.js").read_bytes()
        # a copy identical to the plugin's is not an override: let a plugin upgrade replace it
        if PLUGIN_MERMAID.is_file() and keep_vendor == PLUGIN_MERMAID.read_bytes():
            keep_vendor = None
    if site.is_dir():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    mj = mermaid_js(root, mermaid)
    if keep_vendor is not None and not mermaid and not os.environ.get("DOCS_MERMAID_JS"):
        mj = None  # a fetched or earlier override in the site wins over the plugin copy
    have_mermaid = False
    if keep_vendor is not None and mj is None:
        (site / "vendor").mkdir(exist_ok=True)
        (site / "vendor/mermaid.min.js").write_bytes(keep_vendor)
        have_mermaid = True
    if mj is not None:
        (site / "vendor").mkdir(exist_ok=True)
        if mj.resolve() != (site / "vendor/mermaid.min.js").resolve():
            shutil.copyfile(mj, site / "vendor/mermaid.min.js")
        have_mermaid = True
    written, search = [], []
    all_md = [D.posix(p.relative_to(root)) for p in D.lasting_docs(root)]
    for rel in all_md:
        text = D.read(root / rel)
        fm, body, ok = D.parse_front_matter(text)
        title = fm.get("title") or D.first_h1(body, Path(rel).stem)
        out_rel = rel[len("docs/"):-3] + ".html"
        depth = out_rel.count("/")
        up = "../" * depth
        src_dir = os.path.dirname(rel)

        def fix(t, src_dir=src_dir, out_rel=out_rel):
            if D.is_external(t):
                return t
            path, frag = D.split_target(t)
            if not path:
                return t
            tgt = os.path.normpath(os.path.join(src_dir, path)).replace("\\", "/")
            if tgt.endswith(".md") and tgt.startswith("docs/"):
                return D.relpath(tgt[len("docs/"):-3] + ".html", os.path.dirname(out_rel)) + frag
            if tgt.startswith("docs/"):
                # non-markdown asset: copy next to the page's output
                dst = site / tgt[len("docs/"):]
                src = root / tgt
                if src.is_file() and not tgt.startswith("docs/_site"):
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if not dst.exists():
                        shutil.copyfile(src, dst)
                    return D.relpath(tgt[len("docs/"):], os.path.dirname(out_rel)) + frag
            return t

        meta = ""
        if ok and fm:
            bits = [f"{k}: {D.format_value(fm[k])}" for k in ("status", "version", "owner", "last_verified") if fm.get(k) not in (None, "")]
            if bits:
                meta = f'<p class="meta">{html.escape(" · ".join(bits))}</p>'
        mer = ""
        if have_mermaid and "```mermaid" in body:
            mer = (f'<script src="{up}vendor/mermaid.min.js"></script><script>mermaid.initialize({{startOnLoad:true,'
                   f'theme:(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"default")}});</script>')
        elif "```mermaid" in body:
            mer = '<p class="muted">Diagrams show as source: run <code>docs_index.py fetch-mermaid</code> to draw them offline.</p>'
        html_body = meta + render_markdown(body, fix) + mer
        dest = site / out_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page(title, html_body, up + "../index.html"), encoding="utf-8")
        written.append(D.posix(dest.relative_to(root)))
        search.append({"t": title, "p": "_site/" + out_rel, "k": rel, "x": re.sub(r"[#*`|>\-\[\]()]", " ", body)[:4000]})
    (site / "search-index.js").write_text("window.DOCS_SEARCH=" + json.dumps(search, ensure_ascii=False) + ";", encoding="utf-8")
    return written


def home_page(root: Path, cfg: dict, c: dict) -> str:
    feats = sorted(c["features"], key=lambda f: f["title"].lower())

    def table(items):
        if not items:
            return '<p class="muted">None yet.</p>'
        r = "<table><thead><tr><th>Feature</th><th>Topics</th><th>Status</th><th>Version</th><th>Verified</th></tr></thead><tbody>"
        for f in items:
            href = "_site/" + f["path"][len("docs/"):-3] + ".html"
            lv = html.escape(f["last_verified"] or "never") + (' <span class="stale">stale</span>' if f["stale"] else "")
            r += (f'<tr><td><a href="{html.escape(href)}">{html.escape(f["title"])}</a></td><td>{html.escape(", ".join(f["topics"]))}</td>'
                  f'<td>{html.escape(f["status"])}</td><td>{html.escape(str(f["version"]))}</td><td>{lv}</td></tr>')
        return r + "</tbody></table>"

    parts = ['<h1>Documentation</h1><input id="q" type="search" placeholder="Search the docs" aria-label="Search the docs"><ul class="hits" id="hits"></ul>']
    parts.append('<h2>Start here</h2><ul>')
    for rel, label in (("docs/README.md", "How the docs are kept"), ("docs/overview/README.md", "Overview"), ("docs/features/index.md", "All features")):
        if (root / rel).is_file():
            parts.append(f'<li><a href="_site/{rel[len("docs/"):-3]}.html">{label}</a></li>')
    parts.append("</ul>")
    parts.append("<h2>Features by app</h2>")
    apps = sorted({a for f in feats for a in f["apps"]} | set(cfg.get("apps", [])))
    for a in apps:
        parts.append(f"<h3>{html.escape(a)}</h3>" + table([f for f in feats if a in f["apps"]]))
    parts.append("<h2>Features by topic</h2>")
    topics = sorted({t for f in feats for t in f["topics"]} | set(cfg.get("topics", [])))
    for t in topics:
        parts.append(f"<h3>{html.escape(t)}</h3>" + table([f for f in feats if t in f["topics"]]))
    if not apps and not topics:
        parts.append(table(feats))
    parts.append("<h2>All pages</h2><ul>")
    for d in sorted(c["docs"], key=lambda x: x["path"]):
        parts.append(f'<li><a href="_site/{d["path"][len("docs/"):-3]}.html">{html.escape(d["title"])}</a> <span class="muted">{html.escape(d["path"])}</span></li>')
    parts.append("</ul>")
    parts.append("<h2>Gaps</h2>" + ("<ul>" + "".join(f'<li class="gap">{html.escape(g)}</li>' for g in c["gaps"]) + "</ul>" if c["gaps"] else "<p>None.</p>"))
    js = ('<script src="_site/search-index.js"></script><script>(function(){var q=document.getElementById("q"),h=document.getElementById("hits");'
          'if(!window.DOCS_SEARCH){h.innerHTML="<li class=muted>Search data missing: run docs_index.py build.</li>";}'
          'q.addEventListener("input",function(){var s=q.value.toLowerCase().trim();h.innerHTML="";if(!s||!window.DOCS_SEARCH)return;'
          'var n=0;window.DOCS_SEARCH.forEach(function(d){if(n>=30)return;var hay=(d.t+" "+d.k+" "+d.x).toLowerCase();'
          'if(s.split(/\\s+/).every(function(w){return hay.indexOf(w)>=0})){n++;var li=document.createElement("li"),a=document.createElement("a");'
          'a.href=d.p;a.textContent=d.t;li.appendChild(a);var sp=document.createElement("span");sp.className="muted";sp.textContent=" "+d.k;li.appendChild(sp);h.appendChild(li);}});});})();</script>')
    return page("Documentation", "".join(parts) + js, "index.html", nav="")


def generated_files(root: Path, cfg: dict) -> dict[str, str]:
    c = collect(root, cfg)
    return {
        "docs/features/index.md": feature_index_md(c, cfg),
        "docs/architecture/decisions.md": decisions_md(collect_decisions(root, cfg)),
        "docs/docs-map.json": json.dumps(docs_map(c), indent=2) + "\n",
        "docs/llms.txt": llms_txt(c, cfg),
    }


def build(root: Path, mermaid: str | None = None) -> dict:
    cfg = D.load_config(root)
    # generated markdown first, so the site and the index see it
    gen = generated_files(root, cfg)
    for rel, text in gen.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    c = collect(root, cfg)
    # features/index.md and decisions.md are docs too: re-collect after writing
    gen = generated_files(root, cfg)
    for rel, text in gen.items():
        (root / rel).write_text(text, encoding="utf-8")
    pages = build_site(root, cfg, c, mermaid)
    (root / "docs/index.html").write_text(home_page(root, cfg, c), encoding="utf-8")
    return {"pages": len(pages), "features": len(c["features"]), "gaps": c["gaps"]}


def stale_generated(root: Path) -> list[str]:
    cfg = D.load_config(root)
    bad = []
    for rel, text in generated_files(root, cfg).items():
        f = root / rel
        if not f.is_file() or D.read(f) != text:
            bad.append(rel)
    return bad


def _download(url):
    import urllib.request
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def fetch_mermaid(root, fetch=None) -> int:
    """Download the pinned mermaid; write it only if its SHA-256 matches MERMAID_SHA256."""
    data = (fetch or _download)(MERMAID_URL)
    got = hashlib.sha256(data).hexdigest()
    if got != MERMAID_SHA256:
        print(f"refusing mermaid {MERMAID_VERSION}: SHA-256 is {got}, expected {MERMAID_SHA256}; nothing written", file=sys.stderr)
        return 1
    dest = root / "docs/_site/vendor/mermaid.min.js"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"vendored mermaid {MERMAID_VERSION} to {dest}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "check", "fetch-mermaid"])
    ap.add_argument("--root", default=None)
    ap.add_argument("--mermaid", default=None, help="path to a mermaid.min.js to vendor")
    a = ap.parse_args(argv)
    root = D.repo_root(a.root)
    if a.command == "check":
        bad = stale_generated(root)
        for b in bad:
            print(f"stale generated file: {b} (run docs_index.py build)")
        return 1 if bad else 0
    if a.command == "fetch-mermaid":
        return fetch_mermaid(root)
    r = build(root, a.mermaid)
    print(f"built docs/index.html and {r['pages']} page(s) in docs/_site/; {r['features']} feature(s); {len(r['gaps'])} gap(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
