#!/usr/bin/env python3
"""docs_check: the docs gate (D6 map plus executable checks, DOCSPEC section 8).

  docs_check.py [check] [--base REF] [--strict] [--json] [--no-reference] [--root R]
  docs_check.py map --base REF       code changed without docs (the Stop-hook and gate check)
  docs_check.py drift                doc versus code freshness report (warnings only)

Checks (each finding has a code):
  L1  layout: docs/docs.json, docs/README.md, AGENTS.md, the five overview pages
  F1  feature spec front matter: required keys, status, type, semver, id = folder name,
      apps and topics from docs.json
  K1  every relative link and #anchor resolves; K2 every image has alt text
  S1  every `Source:` path exists; S2 every test path in a "How it is proven" table exists
  V1  a binding doc's front matter version equals the top row of its Versions table
  G1  generated files are fresh (features/index.md, decisions.md, docs-map.json, llms.txt)
  G2  generated reference (docs.json "generated_reference") equals the committed copy
  M1  code mapped to a doc changed on this branch but no doc, change note or `Docs: none` did
  W1  the branch adds files under docs/work/ (branch-only, D9)
  U1  rule-like text in a feature's screens section without a design-system citation (D10);
      a WARNING for now, it becomes an error later (owner decision); put <!-- ux-ok --> on the line to allow it
  T1  last_verified missing or older than stale_days (warning); T2 code newer than doc (warning)
  D1  diagram: a feature spec with no Mermaid block and no image (warning)
  DS1-DS5  design system (R15.7, warnings): README without an order of work (DS1); a numbered version edited after
      approval or without a recorded approval (DS2); layout and missing files (DS3); stale gallery (DS4); duplicate rule IDs (DS5)

Exit 0 when no errors (warnings allowed unless --strict), 1 on errors, 2 on a usage problem.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_lib as D  # noqa: E402
import docs_index as I  # noqa: E402
import design_system as DS  # noqa: E402

ERR, WARN = "error", "warning"
UX_RULE = re.compile(r"\b(must|must not|never|always|should|shall)\b", re.I)
UI_TERM = re.compile(r"\b(button|screen|menu|field|dialog|modal|colou?r|font|icon|tab|toolbar|layout|input|link|label|tooltip|spacing|padding|grid|card)s?\b", re.I)
DS_CITE = re.compile(r"(design[- ]system|\bcomponents?\s+\d+|\brules?\s+\d+|\bDS[-\s]?\d+|\bpatterns?\s+\d+|\btokens?\s+\d+)", re.I)
DOCS_NONE = re.compile(r"^\s*Docs:\s*none\b", re.I | re.M)


class Finding(dict):
    pass


def f(sev, code, path, msg):
    return Finding(severity=sev, code=code, path=path, message=msg)


# -------------------------------------------------------------- the checks
def check_layout(root: Path, cfg: dict) -> list[Finding]:
    out = []
    if not D.has_config(root):
        out.append(f(ERR, "L1", D.CONFIG_REL, "missing: run docs_setup.py init --apply"))
    if not (root / "docs/README.md").is_file():
        out.append(f(ERR, "L1", "docs/README.md", "missing"))
    if not (root / "AGENTS.md").is_file():
        out.append(f(ERR, "L1", "AGENTS.md", "missing (standing agent rules)"))
    for n in ("README.md", "apps.md", "system.md", "glossary.md", "quality.md"):
        if not (root / "docs/overview" / n).is_file():
            out.append(f(ERR, "L1", f"docs/overview/{n}", "missing overview page (D3)"))
    return out


def check_design_system(root: Path, base: str | None) -> list[Finding]:
    return [Finding(x) for x in DS.check(root, base)]


def check_features(root: Path, cfg: dict) -> list[Finding]:
    out = []
    for fd in D.feature_dirs(root):
        rel = D.posix((fd / "spec.md").relative_to(root))
        if not (fd / "spec.md").is_file():
            out.append(f(ERR, "F1", D.posix(fd.relative_to(root)), "feature folder has no spec.md"))
            continue
        text = D.read(fd / "spec.md")
        fm, body, ok = D.parse_front_matter(text)
        if not ok:
            out.append(f(ERR, "F1", rel, "no front matter"))
            continue
        for k in D.FRONT_REQUIRED:
            if k not in fm:
                out.append(f(ERR, "F1", rel, f"front matter lacks `{k}`"))
        if fm.get("id") and fm.get("id") != fd.name:
            out.append(f(ERR, "F1", rel, f"id `{fm.get('id')}` must equal the folder name `{fd.name}`"))
        if fm.get("status") and fm["status"] not in D.STATUSES:
            out.append(f(ERR, "F1", rel, f"status `{fm['status']}` is not one of {', '.join(D.STATUSES)}"))
        if fm.get("type") and fm["type"] not in D.TYPES:
            out.append(f(ERR, "F1", rel, f"type `{fm['type']}` is not one of {', '.join(D.TYPES)}"))
        if fm.get("version") and not D.SEMVER.match(str(fm["version"])):
            out.append(f(ERR, "F1", rel, f"version `{fm['version']}` is not x.y.z"))
        for key, allowed in (("apps", cfg.get("apps")), ("topics", cfg.get("topics"))):
            vals = fm.get(key)
            if vals is not None and not isinstance(vals, list):
                out.append(f(ERR, "F1", rel, f"`{key}` must be a list"))
            elif allowed and isinstance(vals, list):
                for v in vals:
                    if v not in allowed:
                        out.append(f(ERR, "F1", rel, f"{key[:-1]} `{v}` is not in docs.json {key}"))
        if "```mermaid" not in body and not D.IMG_RE.search(body):
            out.append(f(WARN, "D1", rel, "no diagram (Mermaid) and no image"))
        out += check_ux(rel, body)
    return out


def check_ux(rel: str, body: str) -> list[Finding]:
    out = []
    for lvl, title, text in D.sections(body):
        if not re.search(r"\b(screens?|states|ux)\b", title, re.I):
            continue
        in_code = False
        for line in text.split("\n"):
            if line.lstrip().startswith("```"):
                in_code = not in_code
            if in_code or "ux-ok" in line or line.lstrip().startswith(("|", "!", "#")):
                continue
            if UX_RULE.search(line) and UI_TERM.search(line) and not DS_CITE.search(line):
                out.append(f(WARN, "U1", rel, f"rule-like UX text without a design-system citation: {line.strip()[:90]!r}"))
    return out


def check_links(root: Path) -> list[Finding]:
    out = []
    cache: dict[str, set[str]] = {}
    for p in D.lasting_docs(root):
        rel = D.posix(p.relative_to(root))
        text = D.read(p)
        clean = D.strip_code(D.parse_front_matter(text)[1] if text.startswith("---") else text)
        src_dir = os.path.dirname(rel)
        for m in D.IMG_RE.finditer(clean):
            if not m.group(1).strip():
                out.append(f(ERR, "K2", rel, f"image {m.group(2)} has no alt text"))
        targets = [m.group(1) for m in D.LINK_RE.finditer(clean)] + [m.group(2) for m in D.IMG_RE.finditer(clean)]
        for t in targets:
            if D.is_external(t) and not t.startswith("#"):
                continue
            path, frag = D.split_target(t)
            if not path:
                target_rel = rel
            else:
                target_rel = os.path.normpath(os.path.join(src_dir, path)).replace("\\", "/")
            tf = root / target_rel
            if not tf.exists():
                out.append(f(ERR, "K1", rel, f"broken link: {t}"))
                continue
            if frag.startswith("#") and len(frag) > 1 and target_rel.endswith(".md") and tf.is_file():
                if target_rel not in cache:
                    cache[target_rel] = D.anchors(D.read(tf))
                if frag[1:].lower() not in cache[target_rel]:
                    out.append(f(ERR, "K1", rel, f"broken anchor: {t}"))
    return out


def check_sources(root: Path) -> list[Finding]:
    out = []
    for p in D.lasting_docs(root):
        rel = D.posix(p.relative_to(root))
        text = D.read(p)
        fence = False
        for line in text.split("\n"):
            if line.lstrip().startswith(("```", "~~~")):
                fence = not fence
                continue
            if fence:
                continue
            m = re.match(r"^\s*(?:[-*]\s+)?Source:\s*(.+?)\s*$", line)
            if m:
                for tok in re.split(r"[,;]\s*", m.group(1)):
                    tok = tok.strip().strip("`").split(" ")[0].strip("`")
                    if not tok or tok.startswith("<") or "path/to" in tok:
                        continue
                    if ("/" in tok or "." in tok) and not (root / tok).exists():
                        out.append(f(ERR, "S1", rel, f"Source: path does not exist: {tok}"))
        # section "How it is proven": table rows R-ID | test path
        for lvl, title, sec in D.sections(text):
            if re.search(r"how it is proven", title, re.I):
                for line in sec.split("\n"):
                    cells = [c.strip() for c in line.strip().strip("|").split("|")]
                    if len(cells) >= 2 and re.match(r"^R\d+\.\d+", cells[0]):
                        for tok in re.findall(r"`([^`]+)`", cells[1]):
                            tpath = tok.split("::")[0].split(" ")[0]
                            if "path/to" in tpath or not ("/" in tpath or "." in tpath):
                                continue
                            if not (root / tpath).exists():
                                out.append(f(ERR, "S2", rel, f"{cells[0]}: test path does not exist: {tpath}"))
    return out


def check_versions(root: Path, cfg: dict) -> list[Finding]:
    out = []
    for p in D.lasting_docs(root):
        rel = D.posix(p.relative_to(root))
        if not D.is_binding(rel, cfg):
            continue
        fm, body, ok = D.parse_front_matter(D.read(p))
        if not ok or not fm.get("version"):
            continue
        rows = []
        for lvl, title, sec in D.sections(body):
            if title.strip() == "Versions":
                for line in sec.split("\n"):
                    cells = [c.strip() for c in line.strip().strip("|").split("|")]
                    if len(cells) >= 4 and D.SEMVER.match(cells[0]):
                        rows.append(cells[0])
        if rows and rows[0] != str(fm["version"]):
            out.append(f(ERR, "V1", rel, f"front matter version {fm['version']} differs from the top Versions row {rows[0]}: only the release fold writes either"))
    return out


def check_generated(root: Path, cfg: dict, reference: bool) -> list[Finding]:
    out = []
    for rel in I.stale_generated(root):
        out.append(f(ERR, "G1", rel, "generated file is stale: run docs_index.py build"))
    if reference:
        for g in cfg.get("generated_reference", []):
            out += check_reference(root, g)
    return out


def check_reference(root: Path, g: dict) -> list[Finding]:
    name, cmd, outp = g.get("name", "?"), g.get("command"), g.get("output")
    if not cmd or not outp:
        return [f(ERR, "G2", "docs/docs.json", f"generated_reference `{name}` needs command and output")]
    committed = root / outp
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return [f(ERR, "G2", outp, f"`{cmd}` timed out")]
    if r.returncode != 0:
        return [f(ERR, "G2", outp, f"`{cmd}` failed: {r.stderr.strip()[:200]}")]
    if not committed.is_file():
        return [f(ERR, "G2", outp, "committed copy missing")]
    if r.stdout != D.read(committed) and r.stdout.rstrip("\n") != D.read(committed).rstrip("\n"):
        return [f(ERR, "G2", outp, f"generated reference `{name}` is stale: rerun `{cmd}` and commit the output")]
    return []


def check_map(root: Path, cfg: dict, base: str | None) -> list[Finding]:
    """M1: mapped code changed, no doc, note or `Docs: none`."""
    out = []
    mp = root / "docs/docs-map.json"
    if not mp.is_file() or not base:
        return out
    try:
        mapping = json.loads(D.read(mp)).get("map", {})
    except ValueError:
        return [f(ERR, "M1", "docs/docs-map.json", "not valid JSON")]
    changed = D.changed_files(root, base)
    if DOCS_NONE.search(D.commit_messages(root, base)):
        return out
    docs_changed = [c for c in changed if c.startswith("docs/") and not c.startswith("docs/work/") and c not in D.GENERATED]
    hit: dict[str, list[str]] = {}
    for path in changed:
        if path.startswith("docs/"):
            continue
        for g, docs in mapping.items():
            if D.glob_to_regex(g).match(path):
                for d in docs:
                    hit.setdefault(d, []).append(path)
    for doc, paths in sorted(hit.items()):
        base_dir = os.path.dirname(doc)
        touched = any(c == doc or c.startswith(base_dir + "/changes/") or (c.startswith(base_dir + "/changes/" + Path(doc).stem + "/")) for c in docs_changed)
        if not touched:
            out.append(f(ERR, "M1", doc, f"mapped code changed ({paths[0]}{' and ' + str(len(paths) - 1) + ' more' if len(paths) > 1 else ''}) but the doc, a change note or `Docs: none, <reason>` in a commit message did not"))
    roots = cfg.get("code_roots") or []
    if roots:
        mapped = [g for g in mapping]
        for path in changed:
            if any(path.startswith(r.rstrip("/") + "/") for r in roots) and not any(D.glob_to_regex(g).match(path) for g in mapped):
                out.append(f(WARN, "M1", path, "code under a code root that no doc maps (add it to a spec's `code:`)"))
                break
    return out


def check_work_guard(root: Path, base: str | None) -> list[Finding]:
    if not base:
        return []
    bad = [p for p in D.added_files(root, base) if p.startswith("docs/work/")]
    if not bad:
        return []
    return [f(ERR, "W1", bad[0], f"{len(bad)} file(s) under docs/work/ are added on this branch; briefs and reports never reach the default branch (D9). Run docs_work.py strip before the join.")]


def check_freshness(root: Path, cfg: dict) -> list[Finding]:
    out = []
    for fd in D.feature_dirs(root):
        spec = fd / "spec.md"
        if not spec.is_file():
            continue
        rel = D.posix(spec.relative_to(root))
        fm, _b, ok = D.parse_front_matter(D.read(spec))
        if not ok or fm.get("status") in ("retired", "proposed"):
            continue
        lv = str(fm.get("last_verified") or "")
        if I.is_stale(lv, cfg["stale_days"]):
            out.append(f(WARN, "T1", rel, "last_verified is " + (f"{lv}, older than {cfg['stale_days']} days" if lv else "missing")))
        codes = fm.get("code") if isinstance(fm.get("code"), list) else []
        if codes and D.is_git(root):
            cdate = last_commit_date(root, codes)
            ddate = max(filter(None, [D.parse_date(lv), D.parse_date(last_commit_date(root, [rel]) or "")]), default=None)
            cd = D.parse_date(cdate or "")
            if cd and ddate and cd > ddate:
                out.append(f(WARN, "T2", rel, f"code changed {cd.isoformat()} after the doc was last touched or verified ({ddate.isoformat()})"))
    return out


def last_commit_date(root: Path, paths: list[str]) -> str | None:
    specs = [p if "*" not in p and "?" not in p else f":(glob){p}" for p in paths]
    r = D.git(root, "log", "-1", "--format=%cs", "--", *specs)
    s = r.stdout.strip()
    return s or None


def run_checks(root: Path, base: str | None, reference: bool = True) -> list[Finding]:
    cfg = D.load_config(root)
    res = check_layout(root, cfg)
    res += check_features(root, cfg)
    res += check_links(root)
    res += check_sources(root)
    res += check_versions(root, cfg)
    res += check_generated(root, cfg, reference)
    res += check_map(root, cfg, base)
    res += check_work_guard(root, base)
    res += check_freshness(root, cfg)
    res += check_design_system(root, base)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="check", choices=["check", "map", "drift"])
    ap.add_argument("--root", default=None)
    ap.add_argument("--base", default=None, help="git ref of the default branch (default: origin/<default_branch> if it exists)")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-reference", action="store_true", help="skip generated_reference commands")
    a = ap.parse_args(argv)
    root = D.repo_root(a.root)
    if not (root / "docs").is_dir():
        print("no docs/ folder: run docs_setup.py init --apply", file=sys.stderr)
        return 2
    cfg = D.load_config(root)
    base = a.base or D.default_base(root, cfg)
    if a.command == "map":
        res = check_map(root, cfg, base)
    elif a.command == "drift":
        res = check_freshness(root, cfg)
    else:
        res = run_checks(root, base, reference=not a.no_reference)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        for x in sorted(res, key=lambda x: (x["severity"] != ERR, x["code"], x["path"])):
            print(f"{x['severity'].upper():7} {x['code']} {x['path']}: {x['message']}")
        errs = sum(1 for x in res if x["severity"] == ERR)
        print(f"docs_check: {errs} error(s), {len(res) - errs} warning(s)")
    errs = sum(1 for x in res if x["severity"] == ERR)
    if errs or (a.strict and res):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
