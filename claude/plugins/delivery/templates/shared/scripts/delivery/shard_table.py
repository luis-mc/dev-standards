#!/usr/bin/env python3
"""Resolve a CI shard table to the test files of each shard (DL19, CIR10 L3). Library plus a small CLI.

    shard_table.py files --shard-id ID [--table scripts/delivery/ci-shards.json] [--root .] [--join SEP]

Table keys used here (the rest of the format is in CONTRACT.md, "Shard table"):
  timings   path of the timings file (default scripts/delivery/ci-timings.json), seconds per test file
  limits    {"cpus", "memory_gib", "timeout_min"} of the machine a shard runs on
  suites    {"name": {"globs": [...], "exclude": [...], "timings": "path"}}  the test files of one suite
  shards[]  "suite": "name" plus either "part": "K/N" (a balanced share of the suite) or "members": [globs]
            (explicit files); "size": {"cpus", "memory_gib", "workers", "timeout_min"}

A suite's files are cut for each OS on its own: the files that match an explicit `members` glob go to that
shard, the rest are balanced over the `part` shards by recorded timings (`shard_balance.assign`).
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shard_balance as sb  # noqa: E402

DEFAULT_TABLE = "scripts/delivery/ci-shards.json"
SIZE_KEYS = ("cpus", "memory_gib", "workers", "timeout_min")


def load_table(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("shards"), list):
        raise ValueError("the shard table needs a `shards` list")
    return data


def suite_files(suite: dict, root: Path) -> list[str]:
    found: set[str] = set()
    for pattern in suite.get("globs") or []:
        found.update(sb.expand_glob(pattern, root))
    for pattern in suite.get("exclude") or []:
        rx = sb.glob_to_regex(pattern.replace("\\", "/"))
        found = {f for f in found if not rx.match(f)}
    return sorted(found)


def _timings(table: dict, suite: dict, root: Path) -> dict[str, float]:
    rel = suite.get("timings") or table.get("timings") or sb.DEFAULT_TIMINGS
    return sb.load_timings(root / rel)


def _part(text) -> tuple[int, int] | None:
    try:
        return sb.parse_shard(str(text))
    except ValueError:
        return None


def resolve(table: dict, root: Path):
    """Returns (assignment, problems). assignment maps shard id -> sorted files; problems is a list of text."""
    problems: list[str] = []
    suites = table.get("suites") if isinstance(table.get("suites"), dict) else {}
    shards = [s for s in table["shards"] if isinstance(s, dict) and s.get("suite") is not None]
    assignment: dict[str, list[str]] = {}
    owners: dict[tuple, list[str]] = {}
    groups: dict[tuple, list[dict]] = {}
    for sh in shards:
        sid = str(sh.get("id"))
        if sh["suite"] not in suites:
            problems.append("shard %s names the suite %r, which the table does not define" % (sid, sh["suite"]))
            continue
        groups.setdefault((sh["suite"], sh.get("os")), []).append(sh)
    for name, suite in sorted(suites.items()):
        if not any(k[0] == name for k in groups):
            groups.setdefault((name, None), [])
    for (name, os_name), members in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        suite = suites[name]
        files = suite_files(suite, root)
        label = "suite %s%s" % (name, " on %s" % os_name if os_name else "")
        if not files:
            problems.append("%s matches no test files (check its globs)" % label)
        if not members:
            problems.append("%s has no shard: its %d file(s) run nowhere" % (label, len(files)))
        timings = _timings(table, suite, root)
        explicit = [s for s in members if s.get("members") is not None]
        balanced = [s for s in members if s.get("members") is None]
        claimed: set[str] = set()
        for sh in explicit:
            sid = str(sh.get("id"))
            mine: set[str] = set()
            for pattern in sh["members"]:
                rx = sb.glob_to_regex(str(pattern).replace("\\", "/"))
                hit = {f for f in files if rx.match(f)}
                if not hit:
                    problems.append("shard %s: members %r matches no file of %s" % (sid, pattern, label))
                mine |= hit
            assignment[sid] = sorted(mine)
            claimed |= mine
            for f in mine:
                owners.setdefault((name, os_name, f), []).append(sid)
        pool = [f for f in files if f not in claimed]
        parts = [(s, _part(s.get("part"))) for s in balanced]
        for sh, p in parts:
            if p is None:
                problems.append("shard %s needs `part` \"K/N\" or `members` (got %r)" % (sh.get("id"), sh.get("part")))
        valid = [(s, p) for s, p in parts if p is not None]
        if valid:
            total = valid[0][1][1]
            for sh, (k, n) in valid:
                if n != total:
                    problems.append("shard %s: part %d/%d does not match %d/%d of the same suite and OS" %
                                    (sh.get("id"), k, n, valid[0][1][0], total))
            cut = sb.assign(pool, timings, total) if pool else [[] for _ in range(total)]
            for sh, (k, n) in valid:
                if n != total:
                    continue
                sid = str(sh.get("id"))
                assignment[sid] = cut[k - 1]
                for f in cut[k - 1]:
                    owners.setdefault((name, os_name, f), []).append(sid)
            have = {p[0] for _, p in valid if p[1] == total}
            for k in range(1, total + 1):
                if k not in have:
                    problems.append("%s: part %d/%d has no shard, so %d file(s) run nowhere" %
                                    (label, k, total, len(cut[k - 1])))
        elif pool:
            for f in pool:
                owners.setdefault((name, os_name, f), [])
        for f in files:
            owners.setdefault((name, os_name, f), [])
    for (name, os_name, f), who in sorted(owners.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), kv[0][2])):
        where = " on %s" % os_name if os_name else ""
        if not who and (name, os_name) in groups and groups[(name, os_name)]:
            problems.append("%s%s: %s is in no shard" % (name, where, f))
        elif len(who) > 1:
            problems.append("%s%s: %s is in %d shards (%s)" % (name, where, f, len(who), ", ".join(who)))
    problems += _discover_problems(table, root, owners)
    return assignment, sorted(set(problems))


def _discover_problems(table: dict, root: Path, owners: dict) -> list[str]:
    """`discover` lists globs of every test file the repository has; each must be in a suite's shards."""
    patterns = table.get("discover")
    if not patterns:
        return []
    found: set[str] = set()
    for pattern in patterns:
        found.update(sb.expand_glob(pattern, root))
    for pattern in table.get("discover_exclude") or []:
        rx = sb.glob_to_regex(pattern.replace("\\", "/"))
        found = {f for f in found if not rx.match(f)}
    by_file: dict[str, dict[tuple, list[str]]] = {}
    for (name, os_name, f), who in owners.items():
        if who:
            by_file.setdefault(f, {})[(name, os_name)] = who
    out = []
    for f in sorted(found):
        have = by_file.get(f, {})
        if not have:
            out.append("%s is in no shard (no suite takes it)" % f)
            continue
        per_os: dict = {}
        for (name, os_name), who in have.items():
            per_os.setdefault(os_name, []).extend(who)
        for os_name, who in per_os.items():
            if len(set(who)) > 1 and len({k[0] for k in have if k[1] == os_name}) > 1:
                out.append("%s is in %d shards (%s)" % (f, len(set(who)), ", ".join(sorted(set(who)))))
    return out


def size_of(shard: dict, table: dict) -> dict:
    """The shard's size, filled from the table's `limits` for what it leaves out (workers default 1)."""
    limits = table.get("limits") if isinstance(table.get("limits"), dict) else {}
    own = shard.get("size") if isinstance(shard.get("size"), dict) else {}
    size = {k: own.get(k, limits.get(k)) for k in SIZE_KEYS}
    if size["workers"] is None:
        size["workers"] = 1
    return size


def size_problems(shard: dict, table: dict) -> list[str]:
    """Sizing that cannot fit the machine named by `limits`."""
    sid = shard.get("id")
    limits = table.get("limits") if isinstance(table.get("limits"), dict) else {}
    own = shard.get("size") if isinstance(shard.get("size"), dict) else {}
    out = []
    for key in ("cpus", "memory_gib", "timeout_min"):
        for src, label in ((own, "size"),):
            v = src.get(key)
            if v is None:
                continue
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
                out.append("shard %s: size.%s must be a positive number" % (sid, key))
            elif limits.get(key) is not None and v > limits[key]:
                out.append("shard %s: size.%s %s is over the limit %s" % (sid, key, v, limits[key]))
    size = size_of(shard, table)
    w, c = size["workers"], size["cpus"]
    if not isinstance(w, int) or isinstance(w, bool) or w < 1:
        out.append("shard %s: size.workers must be a whole number of 1 or more" % sid)
    elif isinstance(c, (int, float)) and w > c:
        out.append("shard %s: %d workers on %s cpus" % (sid, w, c))
    return out


def estimate_seconds(files: list[str], timings: dict[str, float], workers: int) -> float:
    """Wall-time estimate: recorded seconds of the shard's files, spread over its workers."""
    w = sb.weights(files, timings)
    return sum(w.values()) / max(1, workers)


def cmd_files(args) -> int:
    root = Path(args.root)
    try:
        table = load_table(root / args.table)
        assignment, _ = resolve(table, root)
    except (OSError, ValueError) as exc:
        print("shard_table: %s" % exc, file=sys.stderr)
        return 2
    if args.shard_id not in assignment:
        print("shard_table: shard %r has no suite files in the table" % args.shard_id, file=sys.stderr)
        return 3
    files = assignment[args.shard_id]
    print(args.join.join(files) if args.join is not None else "\n".join(files))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="print the test files of one shard of the table")
    ap.add_argument("action", choices=["files"])
    ap.add_argument("--shard-id", required=True)
    ap.add_argument("--table", default=DEFAULT_TABLE)
    ap.add_argument("--root", default=".")
    ap.add_argument("--join", default=None)
    return cmd_files(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
