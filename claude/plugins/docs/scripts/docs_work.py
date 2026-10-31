#!/usr/bin/env python3
"""docs_work: keep agent briefs and reports off the default branch (D9, DOCSPEC section 10).

  docs_work.py guard --base REF       exit 1 if this branch adds files under docs/work/
                                      (run it on a ready PR to the default branch)
  docs_work.py summaries [--dir D]    one line per report in docs/work/reports/: `- TASK: summary`,
                                      for the release PR body
  docs_work.py strip [--apply]        remove docs/work/ from the working tree and index (the join
                                      step). Dry run by default; prints the summaries first.

Standing rules are not temporary: they live in AGENTS.md, never in docs/work/.
A report's summary line is its `Summary:` line, else its `Status:` line plus the first sentence
under the first heading.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_lib as D  # noqa: E402


def summary_of(text: str) -> str:
    for line in text.split("\n"):
        m = re.match(r"^\s*(?:\*\*)?Summary:(?:\*\*)?\s*(.+)$", line, re.I)
        if m:
            return m.group(1).strip()
    status = ""
    for line in text.split("\n"):
        m = re.match(r"^\s*(?:\*\*)?Status:(?:\*\*)?\s*(.+)$", line, re.I)
        if m:
            status = m.group(1).strip()
            break
    first = ""
    for line in text.split("\n"):
        s = line.strip()
        if s and not s.startswith(("#", "---", "|", "```")) and not re.match(r"^(\*\*)?(Status|Branch):", s, re.I):
            first = re.split(r"(?<=[.!?])\s", s)[0]
            break
    return " ".join(x for x in (f"Status: {status}." if status else "", first) if x).strip()


def summaries(root: Path, sub: str = "docs/work/reports") -> list[str]:
    out = []
    d = root / sub
    if d.is_dir():
        for p in sorted(d.glob("*.md")):
            out.append(f"- {p.stem}: {summary_of(D.read(p))}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["guard", "summaries", "strip"])
    ap.add_argument("--root", default=None)
    ap.add_argument("--base", default=None)
    ap.add_argument("--dir", default="docs/work/reports")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    root = D.repo_root(a.root)
    cfg = D.load_config(root)
    if a.command == "summaries":
        print("\n".join(summaries(root, a.dir)))
        return 0
    if a.command == "guard":
        base = a.base or D.default_base(root, cfg)
        if not base:
            print("no base ref: pass --base", file=sys.stderr)
            return 2
        bad = [p for p in D.added_files(root, base) if p.startswith("docs/work/")]
        for b in bad:
            print(f"added under docs/work/: {b}")
        if bad:
            print(f"{len(bad)} file(s): briefs and reports never reach the default branch; run docs_work.py strip --apply before the join")
        return 1 if bad else 0
    work = root / "docs/work"
    files = [p for p in work.rglob("*") if p.is_file()] if work.is_dir() else []
    s = summaries(root, a.dir)
    if s:
        print("summaries for the PR body:")
        print("\n".join(s))
    print(f"{'removing' if a.apply else 'would remove'} {len(files)} file(s) under docs/work/")
    if not a.apply:
        print("dry run. Add --apply.")
        return 0
    if D.is_git(root):
        D.git(root, "rm", "-r", "-q", "-f", "--ignore-unmatch", "--", "docs/work")
    if work.is_dir():
        shutil.rmtree(work)
    return 0


if __name__ == "__main__":
    sys.exit(main())
