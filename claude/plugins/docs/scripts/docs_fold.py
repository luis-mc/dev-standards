#!/usr/bin/env python3
"""docs_fold: change notes and the release fold (D5, DOCSPEC section 7).

A branch never edits a binding doc's version or version table. It adds a one-line change
note; the release fold writes ONE version row per doc per release.

  docs_fold.py note --doc features/import --task IW21 --change minor --text "Step 3 shows ..." [--section 3] [--breaking]
  docs_fold.py pending                    list notes waiting to be folded (exit 1 if any)
  docs_fold.py fold --release RELEASE-131 [--date YYYY-MM-DD] [--dry-run]

Where notes live:
  features:  docs/features/<feature>/changes/<task>.md
  others:    docs/<area>/changes/<doc>/<task>.md   (for docs/<area>/<doc>.md)

Version rule: per release the highest note wins. major when a note is breaking (or says
change: major), minor when a note adds or changes behaviour, patch for wording and fixes to
the doc only. The fold writes version and date into the front matter and one row at the top
of the doc's `## Versions` table, newest first, then deletes the folded notes.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_lib as D  # noqa: E402

RANK = {"patch": 0, "minor": 1, "major": 2}
HEADER = "| Version | Date | Release | What changed | Tasks |"
SEP = "|---|---|---|---|---|"


def doc_for_notes_dir(rel_dir: str) -> str | None:
    """docs/features/x/changes -> docs/features/x/spec.md; docs/a/changes/d -> docs/a/d.md"""
    parts = rel_dir.split("/")
    if parts[:2] == ["docs", "features"] and len(parts) == 4 and parts[3] == "changes":
        return f"docs/features/{parts[2]}/spec.md"
    if len(parts) == 4 and parts[0] == "docs" and parts[2] == "changes":
        return f"docs/{parts[1]}/{parts[3]}.md"
    return None


def notes_dir_for_doc(doc_arg: str) -> tuple[str, str]:
    """('docs/..../changes', doc path) from `features/x` or `architecture/security`."""
    a = doc_arg.strip().strip("/")
    a = re.sub(r"^docs/", "", a)
    a = re.sub(r"\.md$", "", a)
    parts = a.split("/")
    if parts[0] == "features" and len(parts) == 2:
        return f"docs/features/{parts[1]}/changes", f"docs/features/{parts[1]}/spec.md"
    if parts[0] == "features" and len(parts) == 3 and parts[2] == "spec":
        return f"docs/features/{parts[1]}/changes", f"docs/features/{parts[1]}/spec.md"
    if len(parts) == 2:
        return f"docs/{parts[0]}/changes/{parts[1]}", f"docs/{parts[0]}/{parts[1]}.md"
    raise SystemExit(f"cannot place a change note for {doc_arg!r}: use features/<feature> or <area>/<doc>")


def find_notes(root: Path) -> dict[str, list[Path]]:
    """doc path -> note files (sorted)."""
    out: dict[str, list[Path]] = {}
    docs = root / "docs"
    if not docs.is_dir():
        return out
    for d, dirs, files in os.walk(docs):
        dirs[:] = [x for x in dirs if x not in D.SKIP_DIRS and x != "work"]
        rd = D.posix(Path(d).relative_to(root))
        if os.path.basename(rd) == "changes":
            owner_doc = doc_for_notes_dir(rd)
            if owner_doc:
                notes = sorted(Path(d) / f for f in files if f.endswith(".md") and f.lower() != "readme.md")
                if notes:
                    out.setdefault(owner_doc, []).extend(notes)
        else:
            # docs/<area>/changes/<doc>/
            parent = os.path.basename(os.path.dirname(rd))
            if parent == "changes":
                owner_doc = doc_for_notes_dir(rd)
                if owner_doc:
                    notes = sorted(Path(d) / f for f in files if f.endswith(".md") and f.lower() != "readme.md")
                    if notes:
                        out.setdefault(owner_doc, []).extend(notes)
    return out


def read_note(p: Path) -> dict:
    fm, body, ok = D.parse_front_matter(D.read(p))
    kind = str(fm.get("change", "patch")).strip().lower()
    if kind not in RANK:
        kind = "patch"
    breaking = fm.get("breaking") is True or str(fm.get("breaking", "")).lower() == "true"
    if breaking:
        kind = "major"
    text = " ".join(x.strip() for x in body.strip().split("\n") if x.strip())
    sec = str(fm.get("section", "")).strip()
    if sec and f"section {sec}" not in text.lower() and f"sections {sec}" not in text.lower():
        text = f"{text} (section {sec})" if text else f"section {sec}"
    return {"kind": kind, "text": text, "task": str(fm.get("task") or p.stem), "file": p, "ok": ok}


def bump(version: str, kind: str) -> str:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", str(version or "").strip())
    a, b, c = (int(x) for x in m.groups()) if m else (0, 0, 0)
    if kind == "major":
        return f"{a + 1}.0.0"
    if kind == "minor":
        return f"{a}.{b + 1}.0"
    return f"{a}.{b}.{c + 1}"


def add_row(text: str, row: str) -> str:
    """Insert `row` as the first body row of the Versions table, creating the section."""
    lines = text.rstrip("\n").split("\n")
    idx = next((i for i, l in enumerate(lines) if re.match(r"^##\s+Versions\s*$", l)), None)
    if idx is None:
        return "\n".join(lines + ["", "## Versions", "", "Written by the release fold. Do not edit by hand.", "", HEADER, SEP, row]) + "\n"
    # find the table separator after the heading
    for j in range(idx + 1, len(lines)):
        if re.match(r"^\|\s*-{2,}", lines[j]):
            lines.insert(j + 1, row)
            return "\n".join(lines) + "\n"
        if lines[j].startswith("## "):
            break
    insert_at = idx + 1
    lines[insert_at:insert_at] = ["", "Written by the release fold. Do not edit by hand.", "", HEADER, SEP, row]
    return "\n".join(lines) + "\n"


def plan_fold(root: Path, release: str, date: str) -> list[dict]:
    plan = []
    for doc, files in sorted(find_notes(root).items()):
        f = root / doc
        if not f.is_file():
            plan.append({"doc": doc, "error": "note(s) name a doc that does not exist", "files": files})
            continue
        notes = [read_note(p) for p in files]
        kind = max((n["kind"] for n in notes), key=lambda k: RANK[k])
        fm, _b, _ok = D.parse_front_matter(D.read(f))
        old = str(fm.get("version") or "0.0.0")
        new = bump(old, kind)
        what = "<br>".join(n["text"].replace("|", "\\|") for n in notes if n["text"])
        tasks = ", ".join(sorted({n["task"] for n in notes}))
        plan.append({"doc": doc, "kind": kind, "old": old, "new": new, "row": f"| {new} | {date} | {release} | {what} | {tasks} |", "files": files})
    return plan


def fold(root: Path, release: str, date: str, dry: bool) -> list[dict]:
    plan = plan_fold(root, release, date)
    if dry:
        return plan
    for p in plan:
        if "error" in p:
            continue
        f = root / p["doc"]
        text = D.read(f)
        text = D.set_front_matter(text, {"version": p["new"]})
        text = add_row(text, p["row"])
        f.write_text(text, encoding="utf-8")
        for n in p["files"]:
            rel = D.posix(n.relative_to(root))
            if D.is_git(root) and D.tracked(root, rel):
                if D.git(root, "rm", "-q", "-f", "--", rel).returncode == 0:
                    continue
            n.unlink()
        # drop emptied changes folders
        for n in p["files"]:
            try:
                n.parent.rmdir()
            except OSError:
                pass
    return plan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("note")
    n.add_argument("--doc", required=True)
    n.add_argument("--task", required=True)
    n.add_argument("--change", choices=list(RANK), default="minor")
    n.add_argument("--text", required=True)
    n.add_argument("--section", default="")
    n.add_argument("--breaking", action="store_true")
    n.add_argument("--root", default=None)
    pd = sub.add_parser("pending")
    pd.add_argument("--root", default=None)
    f = sub.add_parser("fold")
    f.add_argument("--release", required=True)
    f.add_argument("--date", default=None)
    f.add_argument("--dry-run", action="store_true")
    f.add_argument("--root", default=None)
    a = ap.parse_args(argv)
    root = D.repo_root(a.root)

    if a.cmd == "note":
        ndir, doc = notes_dir_for_doc(a.doc)
        if not (root / doc).is_file():
            print(f"no such doc: {doc}", file=sys.stderr)
            return 2
        if "\n" in a.text:
            print("a change note is one line", file=sys.stderr)
            return 2
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", a.task).strip("-")
        dest = root / ndir / f"{slug}.md"
        if dest.exists():
            print(f"note exists: {D.posix(dest.relative_to(root))} (edit it, one note per task per doc)", file=sys.stderr)
            return 2
        dest.parent.mkdir(parents=True, exist_ok=True)
        fm = ["---", f"change: {a.change}"]
        if a.breaking:
            fm.append("breaking: true")
        if a.section:
            fm.append(f'section: "{a.section}"')
        fm += [f"task: {a.task}", "---", a.text, ""]
        dest.write_text("\n".join(fm), encoding="utf-8")
        print("wrote", D.posix(dest.relative_to(root)))
        return 0

    if a.cmd == "pending":
        found = find_notes(root)
        for doc, files in found.items():
            print(f"{doc}: {len(files)} note(s) waiting for the release fold")
        return 1 if found else 0

    date = a.date or D.today()
    plan = fold(root, a.release, date, a.dry_run)
    if not plan:
        print("no change notes: nothing to fold")
        return 0
    bad = 0
    for p in plan:
        if "error" in p:
            bad += 1
            print(f"ERROR {p['doc']}: {p['error']}")
            continue
        print(f"{'would fold' if a.dry_run else 'folded'} {p['doc']}: {p['old']} -> {p['new']} ({p['kind']}, {len(p['files'])} note(s))")
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
