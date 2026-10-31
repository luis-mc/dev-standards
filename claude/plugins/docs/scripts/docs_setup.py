#!/usr/bin/env python3
"""docs_setup: lay out a repo's docs/ to DOCSPEC, or move an existing repo to it (D13).

Commands (all dry-run unless --apply):

  init            create the layout in a repo: docs/README.md, the five overview pages,
                  docs/docs.json, AGENTS.md (never over an existing file)
  migrate         plan the scripted move of an existing docs/ tree: old path -> new path.
                  Prints the plan and stops. With --apply: git mv each file, rewrite the
                  relative links in every Markdown/HTML file under docs/ and in the root
                  README/AGENTS/CLAUDE, add front matter stubs to moved feature specs,
                  then run `init` for what is missing.
  move-record     move the artifacts record (docs/work/artifacts or docs/artifacts) to
                  record_dir (default docs/project) and set record_dir in
                  .claude/artifacts.json.

Rules (DOCSPEC section 9):
  * Nothing is deleted. A file whose target exists is left where it is and reported.
  * Moves use `git mv` in a git repo (history is kept), os.rename elsewhere.
  * docs/work/ is never moved: it is branch-only (D9). The plan reports it as a finding.
  * --map OLD=NEW overrides a guessed target; the plan marks guesses as "guess".

Exit 0 on success, 2 on a usage error or a collision under --apply.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_lib as D  # noqa: E402

PLUGIN = Path(__file__).resolve().parent.parent
ARCH_WORDS = re.compile(
    r"(stack|auth|security|data[-_ ]?model|schema|platform|architecture|infra|deploy|hosting|"
    r"privacy|retention|permissions|api[-_ ]?(contract|design)|conventions|decision)", re.I)
RUNBOOK_WORDS = re.compile(r"(runbook|install|release|restore|incident|rollback|deploy[-_ ]?guide|on-?call)", re.I)


def overview_stub(name: str) -> str:
    return (PLUGIN / "templates" / "overview" / name).read_text(encoding="utf-8")


# --------------------------------------------------------------- the plan
def plan_moves(root: Path, cfg: dict, overrides: dict[str, str]) -> tuple[list[dict], list[str]]:
    """[{old,new,guess,why}], findings. Pure: reads the tree, changes nothing."""
    moves: list[dict] = []
    findings: list[str] = []
    record_dir = cfg["record_dir"]

    def add(old: str, new: str, why: str, guess: bool = False):
        moves.append({"old": old, "new": new, "why": why, "guess": guess})

    docs = root / "docs"
    if not docs.is_dir():
        return moves, ["no docs/ folder: nothing to move (use init)"]
    for p in D.iter_files(root, "docs", exts=(".md", ".html", ".json", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".txt", ".css", ".js")):
        rel = D.posix(p.relative_to(root))
        parts = rel.split("/")
        name = parts[-1]
        if rel in overrides:
            add(rel, overrides[rel], "owner override")
            continue
        # branch-only work: never moved. The artifacts record under work/ moves out.
        if rel.startswith("docs/work/artifacts/"):
            add(rel, record_dir + "/" + rel[len("docs/work/artifacts/"):], "artifacts record leaves the branch-only folder (D14)")
            continue
        if rel == "docs/work/agents/BRIEF.md":
            add(rel, "AGENTS.md", "standing agent rules (D9)")
            continue
        if rel.startswith("docs/work/"):
            continue
        if rel.startswith("docs/artifacts/") and record_dir != "docs/artifacts":
            add(rel, record_dir + "/" + rel[len("docs/artifacts/"):], "artifacts record to record_dir (D14)")
            continue
        if rel.startswith("docs/design/specs/"):
            add(rel, "docs/archive/design-specs/" + "/".join(parts[3:]), "app design specs retire; their screens move into feature specs (D10)")
            continue
        if rel.startswith("docs/guides/research/"):
            add(rel, "docs/archive/research/" + "/".join(parts[3:]), "research is archive, never binding")
            continue
        if rel.startswith("docs/guides/notes/") or rel.startswith("docs/notes/"):
            base = "docs/guides/notes/" if rel.startswith("docs/guides/notes/") else "docs/notes/"
            tail = "/".join(parts[len(base.split("/")) - 1:])
            if tail.startswith("runbooks/"):
                continue
            if RUNBOOK_WORDS.search(name):
                add(rel, "docs/guides/runbooks/" + tail, "runbook by name", guess=True)
            elif ARCH_WORDS.search(name):
                add(rel, "docs/architecture/" + tail, "cross-cutting by name", guess=True)
            else:
                add(rel, "docs/guides/" + tail, "notes become guides")
            continue
        if rel.startswith("docs/specs/") and name.endswith(".md"):
            tail = "/".join(parts[2:])
            if "/" in tail:
                add(rel, "docs/architecture/" + tail, "nested spec", guess=True)
            elif name.lower() in ("readme.md", "index.md"):
                continue
            elif ARCH_WORDS.search(name):
                add(rel, "docs/architecture/" + name, "cross-cutting spec by name", guess=True)
            else:
                add(rel, f"docs/features/{Path(name).stem.lower()}/spec.md", "feature spec: one folder per feature (D4)", guess=True)
            continue
        if rel.startswith("docs/specs/"):
            add(rel, "docs/architecture/" + "/".join(parts[2:]), "spec asset", guess=True)
            continue
        if rel.startswith("docs/agents/") or rel.startswith("docs/reports/") or rel.startswith("docs/plans/"):
            findings.append(f"left in place: {rel} (looks like agent working notes; keep them branch-only, see DOCSPEC 8)")
            continue
    # a finding for work/ on the tree
    if (root / "docs/work").is_dir():
        n = sum(1 for _ in (root / "docs/work").rglob("*") if _.is_file())
        if n:
            findings.append(f"docs/work/ holds {n} file(s) that stay in place: it is branch-only (D9). The work guard fails PRs that add more; remove what is there in a separate change.")
    return moves, findings


def resolve_collisions(root: Path, moves: list[dict]) -> tuple[list[dict], list[dict]]:
    ok, skipped, seen = [], [], set()
    for m in moves:
        tgt = root / m["new"]
        if m["old"] == m["new"]:
            continue
        if tgt.exists() or m["new"] in seen:
            skipped.append({**m, "skip": "target exists"})
            continue
        seen.add(m["new"])
        ok.append(m)
    return ok, skipped


# ------------------------------------------------------------ link rewrite
def rewrite_links(root: Path, moves: list[dict], dry: bool = False) -> list[str]:
    """Rewrite relative links in text files so they still resolve after the moves.
    Run AFTER the moves; `moves` gives old -> new. Returns a list of 'file: n links'."""
    o2n = {m["old"]: m["new"] for m in moves}
    n2o = {m["new"]: m["old"] for m in moves}
    # directory prefixes: if every file under a folder moved the same way, a link to the
    # folder follows it. Record prefix maps for whole-folder moves.
    dirmap: dict[str, str] = {}
    for m in moves:
        od, nd = os.path.dirname(m["old"]), os.path.dirname(m["new"])
        if os.path.basename(m["old"]) == os.path.basename(m["new"]) and od != nd:
            dirmap.setdefault(od, nd)
    touched: list[str] = []
    files: list[Path] = list(D.iter_files(root, "docs", exts=(".md", ".html")))
    for extra in ("README.md", "AGENTS.md", "CLAUDE.md"):
        if (root / extra).is_file():
            files.append(root / extra)
    for f in files:
        rel = D.posix(f.relative_to(root))
        old_rel = n2o.get(rel, rel)
        old_dir, new_dir = os.path.dirname(old_rel), os.path.dirname(rel)
        text = D.read(f)
        count = 0

        def fix(target: str) -> str:
            nonlocal count
            if D.is_external(target):
                return target
            path, frag = D.split_target(target)
            if not path:
                return target
            resolved = os.path.normpath(os.path.join(old_dir, path)).replace("\\", "/")
            new_target = o2n.get(resolved)
            if new_target is None:
                for od, nd in dirmap.items():
                    if resolved == od or resolved.startswith(od + "/"):
                        new_target = nd + resolved[len(od):]
                        break
            if new_target is None:
                new_target = resolved
            r = D.relpath(new_target, new_dir)
            if path.endswith("/") and not r.endswith("/"):
                r += "/"
            if r == path:
                return target
            count += 1
            return r + frag

        def md_sub(m):
            full = m.group(0)
            t = m.group(1)
            nt = fix(t)
            return full if nt == t else full.replace("(" + t, "(" + nt, 1)

        def html_sub(m):
            t = m.group(1)
            nt = fix(t)
            return m.group(0) if nt == t else m.group(0).replace(t, nt, 1)

        # protect code fences
        parts = re.split(r"(```.*?```|~~~.*?~~~)", text, flags=re.S)
        for i in range(0, len(parts), 2):
            seg = D.LINK_RE.sub(md_sub, parts[i])
            seg = re.sub(r"\!\[[^\]\n]*\]\(([^)\s]+)[^)]*\)", md_sub, seg)
            seg = D.HREF_RE.sub(html_sub, seg)
            parts[i] = seg
        new_text = "".join(parts)
        if new_text != text:
            touched.append(f"{rel}: {count} link(s)")
            if not dry:
                f.write_text(new_text, encoding="utf-8")
    return touched


# --------------------------------------------------------------- execution
def do_move(root: Path, m: dict) -> None:
    src, dst = root / m["old"], root / m["new"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    if D.is_git(root) and D.tracked(root, m["old"]):
        r = D.git(root, "mv", "--", m["old"], m["new"])
        if r.returncode == 0:
            return
    shutil.move(str(src), str(dst))


def front_matter_stubs(root: Path, moves: list[dict], cfg: dict) -> list[str]:
    done = []
    for m in moves:
        new = m["new"]
        if not re.fullmatch(r"docs/features/[^/]+/spec\.md", new):
            continue
        f = root / new
        text = D.read(f)
        data, body, ok = D.parse_front_matter(text)
        if ok and "id" in data:
            continue
        ver = re.search(r"\*\*Version:\*\*\s*v?(\d+\.\d+\.\d+)", text)
        stub = {
            "id": f.parent.name,
            "title": D.first_h1(text, f.parent.name),
            "apps": [],
            "topics": [],
            "status": "live",
            "version": ver.group(1) if ver else "0.1.0",
            "owner": "owner",
            "type": "reference",
            "code": [],
        }
        f.write_text(D.set_front_matter(text, stub), encoding="utf-8")
        done.append(new)
    return done


def write_if_absent(root: Path, rel: str, content: str, created: list[str], skipped: list[str]) -> None:
    f = root / rel
    if f.exists():
        skipped.append(rel)
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    created.append(rel)


def init_layout(root: Path, cfg_in: dict | None = None, apply: bool = True) -> tuple[list[str], list[str]]:
    created: list[str] = []
    skipped: list[str] = []
    cfg = dict(D.DEFAULTS)
    cfg.update(cfg_in or {})
    if apply:
        write_if_absent(root, D.CONFIG_REL, json.dumps({k: cfg[k] for k in (
            "schema", "docspec", "apps", "topics", "record_dir", "default_branch", "stale_days")}, indent=2) + "\n", created, skipped)
        write_if_absent(root, "docs/README.md", (PLUGIN / "templates" / "docs-readme.md").read_text(encoding="utf-8"), created, skipped)
        for n in ("README.md", "apps.md", "system.md", "glossary.md", "quality.md"):
            write_if_absent(root, "docs/overview/" + n, overview_stub(n), created, skipped)
        for d in ("features", "design-system", "architecture/decisions", "guides/runbooks", "reference", "archive"):
            keep = root / "docs" / d / ".gitkeep"
            if not (root / "docs" / d).exists():
                keep.parent.mkdir(parents=True, exist_ok=True)
                keep.write_text("", encoding="utf-8")
                created.append(f"docs/{d}/")
        write_if_absent(root, "AGENTS.md", (PLUGIN / "templates" / "AGENTS.md").read_text(encoding="utf-8"), created, skipped)
        _ensure_gitignore(root, created)
    return created, skipped


def _ensure_gitignore(root: Path, created: list[str]) -> None:
    gi = root / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    if "docs/_site/" not in text.split("\n"):
        gi.write_text(text + ("" if text.endswith("\n") or not text else "\n") + "docs/_site/\n", encoding="utf-8")
        created.append(".gitignore (docs/_site/)")


def move_record(root: Path, cfg: dict, apply: bool) -> dict:
    target = cfg["record_dir"]
    src = None
    for cand in ("docs/work/artifacts", "docs/artifacts"):
        if cand != target and (root / cand).is_dir():
            src = cand
            break
    out = {"from": src, "to": target, "moved": 0, "skipped": []}
    if src is None:
        return out
    moves = []
    for p in sorted((root / src).rglob("*")):
        if p.is_file():
            rel = D.posix(p.relative_to(root))
            moves.append({"old": rel, "new": target + rel[len(src):], "why": "record", "guess": False})
    ok, skipped = resolve_collisions(root, moves)
    out["skipped"] = [s["old"] for s in skipped]
    out["moved"] = len(ok)
    out["plan"] = [(m["old"], m["new"]) for m in ok]
    if apply:
        for m in ok:
            do_move(root, m)
        rewrite_links(root, ok)
        af = root / ".claude" / "artifacts.json"
        data = {}
        if af.is_file():
            try:
                data = json.loads(D.read(af))
            except ValueError:
                data = {}
        data["record_dir"] = target
        af.parent.mkdir(parents=True, exist_ok=True)
        af.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        # drop the emptied source folder only when it holds no files (never deletes content)
        for d, _dirs, _files in os.walk(root / src, topdown=False):
            try:
                os.rmdir(d)
            except OSError:
                pass
    return out


# --------------------------------------------------------------------- CLI
def parse_overrides(items) -> dict[str, str]:
    out = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"--map needs OLD=NEW, got {it!r}")
        a, b = it.split("=", 1)
        out[a.strip()] = b.strip()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["init", "migrate", "move-record"])
    ap.add_argument("--root", default=None)
    ap.add_argument("--apply", action="store_true", help="make the changes (default: print the plan only)")
    ap.add_argument("--map", action="append", help="OLD=NEW: force a target for one file")
    ap.add_argument("--app", action="append", default=None, help="init: an app name (repeatable)")
    ap.add_argument("--topic", action="append", default=None, help="init: a topic name (repeatable)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = D.repo_root(a.root)
    cfg = D.load_config(root)

    if a.command == "init":
        extra = {}
        if a.app:
            extra["apps"] = a.app
        if a.topic:
            extra["topics"] = a.topic
        if a.apply:
            created, skipped = init_layout(root, extra)
            print("created:" if created else "nothing to create")
            for c in created:
                print("  +", c)
            for s in skipped:
                print("  = kept (exists):", s)
        else:
            print("dry run: init would create docs/docs.json, docs/README.md, docs/overview/*.md (5), the folders, AGENTS.md (if absent) and ignore docs/_site/. Add --apply.")
        return 0

    if a.command == "move-record":
        r = move_record(root, cfg, a.apply)
        if a.json:
            print(json.dumps(r, indent=2))
        else:
            if r["from"] is None:
                print(f"no record folder to move (record_dir is {r['to']})")
            else:
                print(f"{'moved' if a.apply else 'would move'} {r['moved']} file(s): {r['from']} -> {r['to']}")
                for s in r["skipped"]:
                    print("  kept (target exists):", s)
                if not a.apply:
                    print("dry run. Add --apply.")
        return 0

    # migrate
    overrides = parse_overrides(a.map)
    moves, findings = plan_moves(root, cfg, overrides)
    ok, skipped = resolve_collisions(root, moves)
    print(f"docs migration plan for {root} ({'APPLY' if a.apply else 'dry run'})")
    print(f"  {len(ok)} move(s), {len(skipped)} skipped, {len(findings)} finding(s)")
    for m in ok:
        print(f"  mv {m['old']} -> {m['new']}   [{m['why']}{', guess' if m['guess'] else ''}]")
    for s in skipped:
        print(f"  skip {s['old']} -> {s['new']}   [{s['skip']}; file kept]")
    for f in findings:
        print("  note:", f)
    if not a.apply:
        print("dry run: nothing changed. Review, add --map OLD=NEW for any guess you disagree with, then run with --apply.")
        return 0
    for m in ok:
        do_move(root, m)
    touched = rewrite_links(root, ok)
    stubs = front_matter_stubs(root, ok, cfg)
    created, kept = init_layout(root)
    print(f"moved {len(ok)} file(s); rewrote links in {len(touched)} file(s); front matter stubs: {len(stubs)}; created: {len(created)}")
    for t in touched:
        print("  links:", t)
    for c in created:
        print("  +", c)
    print("next: run docs_index.py build, then docs_check.py; the gaps list shows what content is missing (D13).")
    return 2 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
