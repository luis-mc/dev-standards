#!/usr/bin/env python3
"""Plan-to-tasks check (DRAFT, not wired into a hook).

Every numbered plan row and every audit finding listed in an agent's report must become a tracked task in
the project's task registry, in the same turn. No periodic audit: this check runs on the report that was
just written. It reads; it never writes the registry (only task-add does) and never commits.

    plan_rows_check.py REPORT.md [REPORT.md ...] [--registry PATH] [--tag TAG] [--json] [--commands]

How a row is found (Markdown only):
  - a table row whose first cell is a number or an ID such as `3`, `B07` or `WB1`
        | 3 | Change ... | files | hours | ... |
  - a numbered list item `1. text` or `1) text`
The row key is `<tag>#<id>`. The tag is the report's folder name when the report is `plan.md`, `audit.md` or
`report.md` inside a folder, else the file name without its extension (override with --tag, one report only).

A row is tasked when the item or the detail of a registry task contains its key (for example
`DSY97#3` in the detail). So the rule when you task a row is: put the key in the task detail.

Exit 0 when every row is tasked; 1 when some are not (the keys are listed, with --commands a task-add line for
each); 2 on a usage error. Rows of a table or list in a section titled like "not proposed", "out of scope" or
"what stays" are skipped. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROW_ID = r"(?:\d{1,3}|[A-Z]{1,6}\d{1,4})"
TABLE_ROW_RE = re.compile(r"^\|\s*(" + ROW_ID + r")\s*\|\s*(.+?)\s*\|?\s*$")
LIST_ROW_RE = re.compile(r"^\s{0,3}(\d{1,3})[.)]\s+(.+)$")
HEADING_RE = re.compile(r"^#{1,6}\s*(.+?)\s*$")
SKIP_SECTION_RE = re.compile(r"not proposed|out of scope|what stays|non-goals?|rejected", re.I)
GENERIC_NAMES = {"plan", "audit", "report", "findings", "readme"}


def tag_for(path: Path) -> str:
    stem = path.stem
    if stem.lower() in GENERIC_NAMES and path.parent.name:
        return path.parent.name
    return stem


def find_rows(text: str, tag: str) -> list[dict]:
    """The numbered rows of one report: key, id, text."""
    rows: list[dict] = []
    skipping = False
    for line in text.splitlines():
        h = HEADING_RE.match(line)
        if h:
            skipping = bool(SKIP_SECTION_RE.search(h.group(1)))
            continue
        if skipping:
            continue
        m = TABLE_ROW_RE.match(line) or LIST_ROW_RE.match(line)
        if m:
            rid = m.group(1)
            body = re.sub(r"[*_`]", "", m.group(2).split("|")[0]).strip()
            rows.append({"key": f"{tag}#{rid}", "id": rid, "text": body})
    seen: set[str] = set()
    unique = []
    for r in rows:
        if r["key"] not in seen:
            seen.add(r["key"])
            unique.append(r)
    return unique


def record_dir(root: Path) -> Path:
    try:
        cfg = json.loads((root / ".claude" / "artifacts.json").read_text(encoding="utf-8"))
        rel = cfg.get("record_dir")
        if isinstance(rel, str) and rel:
            return root / rel
    except (OSError, ValueError):
        pass
    return root / "docs" / "artifacts"


def load_tasks(registry: Path) -> list[dict]:
    data = json.loads(registry.read_text(encoding="utf-8"))
    tasks = data.get("tasks", []) if isinstance(data, dict) else []
    return [t for t in tasks if isinstance(t, dict)]


def untasked(rows: list[dict], tasks: list[dict]) -> list[dict]:
    """Rows whose key is in no task's item or detail."""
    blob = [(str(t.get("item", "")) + "\n" + str(t.get("detail", ""))) for t in tasks]
    return [r for r in rows if not any(r["key"] in b for b in blob)]


def task_add_line(row: dict) -> str:
    item = row["text"][:60]
    return f'task-add --owner project --item "{item}" --detail "{row["key"]}: {row["text"][:200]}" --expected "DD Mon"'


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--registry", default=None, help="path to registry.json (default: the project's record folder)")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--commands", action="store_true", help="print a task-add line for each row without a task")
    a = ap.parse_args(argv)
    if a.tag and len(a.reports) > 1:
        print("--tag works with one report only", file=sys.stderr)
        return 2
    registry = Path(a.registry) if a.registry else record_dir(Path.cwd()) / "registry.json"
    try:
        tasks = load_tasks(registry)
    except (OSError, ValueError) as e:
        print(f"cannot read the registry {registry}: {e}", file=sys.stderr)
        return 2
    missing: list[dict] = []
    total = 0
    for rep in a.reports:
        p = Path(rep)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            print(f"cannot read {rep}: {e}", file=sys.stderr)
            return 2
        rows = find_rows(text, a.tag or tag_for(p))
        total += len(rows)
        missing.extend(untasked(rows, tasks))
    if a.json:
        print(json.dumps({"rows": total, "untasked": missing}, indent=2))
    else:
        print(f"{total} numbered rows, {len(missing)} without a task")
        for r in missing:
            print(f"  {r['key']}: {r['text'][:100]}")
            if a.commands:
                print("    " + task_add_line(r))
        if missing:
            print("Task each row now (task-add, put the key in the detail), or drop it with a reason in the report.")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
