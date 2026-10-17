#!/usr/bin/env python3
"""Split test files into shards of about equal run time (STACKSPEC 13.1, CI speed-ups).

    shard_balance.py --shard K/N [--timings FILE] [--glob PATTERN]... [--files-from FILE|-] [FILE...]
    shard_balance.py update --report FILE... [--timings FILE] [--format auto|vitest|playwright]

Split: the test files come from the arguments, `--files-from` (one per line, `-` is stdin) and
`--glob` patterns (`**` allowed, relative to `--root`, default the current directory). They are
assigned greedily, longest first, each to the shard with the least seconds so far (ties go to the
lower shard number), and the files of shard K (1-based) are printed, sorted, one per line
(`--join SEP` prints them on one line). The seconds come from the committed timings file
(default `scripts/delivery/ci-timings.json`; `{"seconds": {"path": 12.3}}` or a plain
`{"path": 12.3}`). A file without a measurement gets the median of the measured files in the
list (the median of the whole timings file when none of them is measured, else 1 second), so a new
file lands somewhere sensible and the same input always gives the same shards. A missing timings
file is not an error: every file then weighs the same.

Update: `update` folds a test runner's JSON report (vitest or jest `testResults[]` with
`startTime`/`endTime`, or Playwright's JSON reporter with per-test `duration`) into the timings
file. A file seen in several reports is averaged; a file the reports did not measure keeps its old
figure; with `--prune-missing` files that no longer exist under `--root` are dropped. Run it on
the reports the shards upload, then commit the file.

Exit: 0 ok; 2 usage error or an unreadable report/timings file; 3 `--glob` matched nothing and no
file was given.
Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import statistics
import sys
from pathlib import Path

DEFAULT_TIMINGS = "scripts/delivery/ci-timings.json"
EXIT_USAGE = 2
EXIT_NO_FILES = 3


def glob_to_regex(pattern: str) -> "re.Pattern[str]":
    """`**/` = any directories (or none), `**` = anything, `*` = within one segment, `?` = one character."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def expand_glob(pattern: str, root: Path) -> list[str]:
    rx = glob_to_regex(pattern.replace("\\", "/"))
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git")]
        for name in filenames:
            rel = Path(dirpath, name).relative_to(root).as_posix()
            if rx.match(rel):
                found.append(rel)
    return sorted(found)


def load_timings(path: Path) -> dict[str, float]:
    """Seconds per file; a missing file is an empty map, an unreadable one an error."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("seconds"), dict):
        data = data["seconds"]
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected an object of seconds per file")
    return {k.replace("\\", "/"): float(v) for k, v in data.items() if not k.startswith("_")}


def weights(files: list[str], timings: dict[str, float]) -> dict[str, float]:
    known = [timings[f] for f in files if f in timings]
    if known:
        fill = statistics.median(known)
    elif timings:
        fill = statistics.median(timings.values())
    else:
        fill = 1.0
    return {f: timings.get(f, fill) for f in files}


def assign(files: list[str], timings: dict[str, float], shards: int) -> list[list[str]]:
    """Greedy longest-first: every file goes to the lightest shard so far. Deterministic."""
    w = weights(sorted(set(files)), timings)
    totals = [0.0] * shards
    out: list[list[str]] = [[] for _ in range(shards)]
    for f in sorted(w, key=lambda f: (-w[f], f)):
        k = min(range(shards), key=lambda i: (totals[i], i))
        totals[k] += w[f]
        out[k].append(f)
    return [sorted(s) for s in out]


# --------------------------------------------------------------------------- update


def _rel(name: str, root: Path) -> str:
    """Repository-relative path with `/` separators."""
    p = Path(name.replace("\\", "/"))
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(root.resolve())
        except ValueError:
            return p.as_posix()
    return posixpath.normpath(p.as_posix())


def seconds_from_vitest(report: dict, root: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in report.get("testResults") or []:
        a, b = r.get("startTime"), r.get("endTime")
        if a is None or b is None or "name" not in r:
            continue
        out[_rel(r["name"], root)] = round(max(0, b - a) / 1000, 1)
    return out


def seconds_from_playwright(report: dict, root: Path) -> dict[str, float]:
    out: dict[str, float] = {}

    def walk(suite: dict, file: str | None) -> None:
        file = suite.get("file") or file
        for spec in suite.get("specs") or []:
            f = spec.get("file") or file
            for t in spec.get("tests") or []:
                for res in t.get("results") or []:
                    if f is not None:
                        out[f] = out.get(f, 0.0) + res.get("duration", 0) / 1000
        for child in suite.get("suites") or []:
            walk(child, file)

    for s in report.get("suites") or []:
        walk(s, None)
    base = report.get("config", {}).get("rootDir")
    result = {}
    for f, sec in out.items():
        path = Path(base, f) if base and not Path(f).is_absolute() else Path(f)
        result[_rel(str(path), root)] = round(sec, 1)
    return result


def seconds_from_report(report: dict, fmt: str, root: Path) -> dict[str, float]:
    if fmt == "auto":
        fmt = "vitest" if "testResults" in report else "playwright"
    if fmt == "vitest":
        return seconds_from_vitest(report, root)
    if fmt == "playwright":
        return seconds_from_playwright(report, root)
    raise ValueError(f"unknown report format {fmt!r}")


def merge(old: dict[str, float], fresh: list[dict[str, float]], keep=lambda f: True) -> dict[str, float]:
    sums: dict[str, list[float]] = {}
    for run in fresh:
        for f, s in run.items():
            sums.setdefault(f, []).append(s)
    merged = dict(old)
    for f, vals in sums.items():
        merged[f] = round(sum(vals) / len(vals), 1)
    return dict(sorted((f, s) for f, s in merged.items() if keep(f)))


def cmd_update(args: argparse.Namespace) -> int:
    root = Path(args.root)
    path = Path(args.timings)
    try:
        old = load_timings(path)
        fresh = [seconds_from_report(json.loads(Path(r).read_text(encoding="utf-8")), args.format, root)
                 for r in args.report]
    except (OSError, ValueError) as e:
        print(f"shard_balance: {e}", file=sys.stderr)
        return EXIT_USAGE
    keep = (lambda f: (root / f).exists()) if args.prune_missing else (lambda f: True)
    seconds = merge(old, fresh, keep)
    path.parent.mkdir(parents=True, exist_ok=True)
    note = "Seconds per test file; refreshed by `shard_balance.py update` from a runner's JSON report."
    path.write_text(json.dumps({"_note": note, "seconds": seconds}, indent=1) + "\n", encoding="utf-8")
    print(f"shard_balance: {len(seconds)} files in {path}, {len(args.report)} reports merged")
    return 0


# --------------------------------------------------------------------------- split


def parse_shard(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)/(\d+)", text)
    if not m or int(m.group(2)) < 1 or not 1 <= int(m.group(1)) <= int(m.group(2)):
        raise ValueError(f"--shard must be K/N with 1 <= K <= N, got {text!r}")
    return int(m.group(1)), int(m.group(2))


def cmd_split(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        k, n = parse_shard(args.shard)
        timings = load_timings(Path(args.timings))
    except (OSError, ValueError) as e:
        print(f"shard_balance: {e}", file=sys.stderr)
        return EXIT_USAGE
    files = [f.replace("\\", "/") for f in args.files]
    if args.files_from:
        text = sys.stdin.read() if args.files_from == "-" else Path(args.files_from).read_text(encoding="utf-8")
        files += [ln.strip().replace("\\", "/") for ln in text.splitlines() if ln.strip()]
    for pattern in args.glob:
        files += expand_glob(pattern, root)
    if not files:
        print("shard_balance: no test files (nothing given, or the glob matched nothing)", file=sys.stderr)
        return EXIT_NO_FILES
    mine = assign(files, timings, n)[k - 1]
    if args.join is not None:
        print(args.join.join(mine))
    else:
        for f in mine:
            print(f)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "update":
        p = argparse.ArgumentParser(prog="shard_balance.py update", description="refresh the timings file from reports")
        p.add_argument("--report", nargs="+", required=True)
        p.add_argument("--timings", default=DEFAULT_TIMINGS)
        p.add_argument("--format", default="auto", choices=["auto", "vitest", "playwright"])
        p.add_argument("--root", default=".")
        p.add_argument("--prune-missing", action="store_true")
        return cmd_update(p.parse_args(argv[1:]))
    p = argparse.ArgumentParser(description="print the test files of one balanced shard")
    p.add_argument("--shard", required=True, help="K/N, 1-based")
    p.add_argument("--timings", default=DEFAULT_TIMINGS)
    p.add_argument("--glob", action="append", default=[])
    p.add_argument("--files-from")
    p.add_argument("--root", default=".")
    p.add_argument("--join", default=None, help="print the files on one line, separated by this")
    p.add_argument("files", nargs="*")
    return cmd_split(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
