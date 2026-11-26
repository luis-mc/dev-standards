#!/usr/bin/env python3
"""DL-116 (DS261): a workflow the delivery watcher requires has no pull-request path filter.

    ci_areas_check.py [--root DIR] [--config .delivery/config.json] [--workflow NAME ...]

A `paths` or `paths-ignore` filter under `pull_request` (or `pull_request_target`) makes GitHub start no run at
all for a change that only touches the filtered paths. The watcher then sees no run of a required workflow
(DL-03) and the pull request waits for nothing. The filter also ignores `.delivery/**`, which the lifecycle
release check reads (DL-112, DL-113). Skip work with a job-level `if` on the outputs of changed_areas.py and
an aggregate job that always runs and is the required check (`templates/shared/ci-areas-pattern.yml`).

The required workflows are `watcher.ci_workflows` in `.delivery/config.json`, or the `--workflow` names. With
neither, nothing is required and the check passes. A filter under `push` is allowed: ci_skip_check.py reads it.
Exit 0 pass, 1 a required workflow has a pull-request filter, 2 bad input. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EVENTS = ("pull_request", "pull_request_target")
FILTERS = ("paths", "paths-ignore")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def pr_filters(text: str) -> list:
    """['pull_request.paths-ignore', ...]: the path filters under the pull-request events of the `on:` block."""
    lines = [ln.rstrip("\r") for ln in text.split("\n")]
    useful = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    start = next((k for k, ln in enumerate(useful) if re.fullmatch(r"""["']?on["']?:\s*(#.*)?""", ln)), None)
    if start is None:
        return []
    block = []
    for ln in useful[start + 1:]:
        if _indent(ln) == 0:
            break
        block.append(ln)
    found = []
    for k, ln in enumerate(block):
        m = re.fullmatch(r"  (pull_request|pull_request_target):\s*(#.*)?", ln)
        if not m or _indent(ln) != 2:
            continue
        for inner in block[k + 1:]:
            if _indent(inner) <= 2:
                break
            f = re.fullmatch(r"    (paths|paths-ignore):.*", inner)
            if f:
                found.append("%s.%s" % (m.group(1), f.group(1)))
    return found


def findings(text: str, name: str) -> list:
    return ["%s: `%s` filter at workflow level; use a job-level `if` and an aggregate job" % (name, f)
            for f in pr_filters(text)]


def required(root: Path, config: Path, names: list) -> list:
    if names:
        return names
    try:
        cfg = json.loads(config.read_text(encoding="utf-8"))
    except OSError:
        return []
    except ValueError as e:
        raise ValueError("%s is not valid JSON: %s" % (config, e))
    got = ((cfg.get("watcher") or {}).get("ci_workflows")) if isinstance(cfg, dict) else None
    return [str(n) for n in got] if isinstance(got, list) else []


def check(root: Path, names: list) -> list:
    out = []
    for n in names:
        f = root / ".github" / "workflows" / n
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            out.append("%s: required workflow file not found" % n)
            continue
        out += findings(text, n)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default=None)
    ap.add_argument("--workflow", action="append", default=[])
    a = ap.parse_args(argv)
    root = Path(a.root)
    try:
        names = required(root, Path(a.config) if a.config else root / ".delivery" / "config.json", a.workflow)
    except ValueError as e:
        print("ci_areas_check: %s" % e, file=sys.stderr)
        return 2
    if not names:
        print("OK ci_areas_check: no required workflow listed (watcher.ci_workflows)")
        return 0
    problems = check(root, names)
    for p in problems:
        print("FAIL " + p)
    if not problems:
        print("OK ci_areas_check: %d required workflow%s have no pull-request path filter"
              % (len(names), "" if len(names) == 1 else "s"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
