#!/usr/bin/env python3
"""The Windows-only test table and its guard (CIR10 W3).

    windows_real.py check [--table windows-real.json] [--shards ci-shards.json] [--root DIR]
    windows_real.py files [--table windows-real.json]

Only a test that needs a real Windows machine runs on Windows. Every other test
runs on Linux. `windows-real.json` lists those tests:

    {"schema": 1, "cap": 12, "max_minutes": 5,
     "files": [{"path": "tests/acl.test.ts", "marker": "icacls", "why": "real ACLs", "minutes": 0.3}]}

`check` fails (exit 1) when:
  - a listed file is missing, listed twice, has no marker, or no longer contains its marker
    (the Windows-only check was removed, so the file does not need Windows any more);
  - the table holds more files than `cap`, or the `minutes` add up to more than `max_minutes`;
  - a shard with `"os": "windows"` is not the table's shard: it needs `"set": "windows-real"`,
    may run only the command `@windows-real`, and may list `files` only from the table.
    Anything else on Windows is refused.

`files` prints the listed paths, one per line, as relative paths with forward slashes.
Exit: 0 passed, 1 a rule broken, 2 a file cannot be read. Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SET_NAME = "windows-real"
COMMAND = "@windows-real"
DEFAULT_TABLE = "windows-real.json"
DEFAULT_SHARDS = "ci-shards.json"


class TableError(Exception):
    pass


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TableError("cannot read %s: %s" % (path, exc))
    if not isinstance(data, dict):
        raise TableError("%s is not a JSON object" % path)
    return data


def norm(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def check_table(table: dict, root: Path) -> list[str]:
    problems: list[str] = []
    files = table.get("files")
    if not isinstance(files, list):
        return ['the table has no "files" list']
    cap = table.get("cap")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
        problems.append('"cap" must be a whole number')
    elif len(files) > cap:
        problems.append("%d files are listed, the cap is %d" % (len(files), cap))
    seen: set[str] = set()
    total = 0.0
    for entry in files:
        path = norm(entry.get("path", "")) if isinstance(entry, dict) else ""
        if not path:
            problems.append("an entry has no path")
            continue
        if path in seen:
            problems.append("%s is listed twice" % path)
        seen.add(path)
        marker = entry.get("marker")
        if not isinstance(marker, str) or not marker:
            problems.append("%s has no marker (the text that makes it Windows-only)" % path)
        mins = entry.get("minutes", 0)
        if isinstance(mins, (int, float)) and not isinstance(mins, bool):
            total += mins
        full = root / path
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            problems.append("%s is listed but does not exist" % path)
            continue
        if isinstance(marker, str) and marker and marker.lower() not in text.lower():
            problems.append("%s no longer contains its marker %r: move it to Linux or fix the marker" % (path, marker))
    limit = table.get("max_minutes")
    if isinstance(limit, (int, float)) and not isinstance(limit, bool) and total > limit:
        problems.append("the listed tests add up to %g minutes, the limit is %g" % (total, limit))
    return problems


def check_shards(shards_doc: dict, table: dict) -> list[str]:
    problems: list[str] = []
    listed = {norm(e.get("path", "")) for e in table.get("files", []) if isinstance(e, dict)}
    for shard in shards_doc.get("shards", []):
        if not isinstance(shard, dict) or shard.get("os") != "windows":
            continue
        sid = shard.get("id", "?")
        if shard.get("set") != SET_NAME:
            problems.append('windows shard %r must have "set": "%s"; nothing else runs on Windows' % (sid, SET_NAME))
        cmds = shard.get("commands", [])
        if cmds != [COMMAND]:
            problems.append("windows shard %r may run only %s, it runs %r" % (sid, COMMAND, cmds))
        for f in shard.get("files", []):
            if norm(f) not in listed:
                problems.append("windows shard %r names %s, which is not in the table" % (sid, f))
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="windows_real.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "files"):
        p = sub.add_parser(name)
        p.add_argument("--table", default=DEFAULT_TABLE)
        p.add_argument("--root", default=".")
        if name == "check":
            p.add_argument("--shards", default=DEFAULT_SHARDS)
    args = ap.parse_args(argv)
    root = Path(args.root)
    try:
        table = load_json(root / args.table)
        if args.cmd == "files":
            for e in table.get("files", []):
                print(norm(e["path"]))
            return 0
        problems = check_table(table, root)
        shards = root / args.shards
        if shards.exists():
            problems += check_shards(load_json(shards), table)
    except TableError as exc:
        print("windows_real: %s" % exc, file=sys.stderr)
        return 2
    for p in problems:
        print("windows_real: %s" % p, file=sys.stderr)
    if problems:
        return 1
    print("windows_real: ok (%d file(s) need Windows)" % len(table.get("files", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
