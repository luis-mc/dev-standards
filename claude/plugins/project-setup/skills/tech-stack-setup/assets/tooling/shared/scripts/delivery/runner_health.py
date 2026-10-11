#!/usr/bin/env python3
"""Runner health (STACKSPEC 13.1): are there online runners for the labels CI needs?

Used by join.py (before the train is called ready for its ready pull request) and
ci_watch.py (a job queued too long). It only ever warns; it never blocks (D5).

    runner_health.py [--repo OWNER/NAME] [--json]

reads the `runs-on` of every job in .github/workflows/*.yml|yaml, resolves
`${{ fromJSON(vars.NAME || '"default"') }}` through the repository variable when
`gh` can read it, and lists the repository's online runners with
`gh api repos/{owner}/{repo}/actions/runners`. GitHub-hosted labels (ubuntu-*,
windows-*, macos-*) count as available. A label set with `self-hosted` needs one
online runner that carries every label of the set. Without permission to list
runners (it needs admin rights) the check is skipped and says why.

Exit: 0 always when it could run (warnings are printed), 2 usage error.
Python 3.11+, standard library only; `gh` is optional.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOSTED_PREFIXES = ("ubuntu-", "windows-", "macos-")
GH_TIMEOUT = 30

_EXPR = re.compile(
    r"^\$\{\{\s*(?P<json>fromJSON\(\s*)?vars\.(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s*\|\|\s*'(?P<default>(?:[^']|'')*)')?\s*\)?\s*\}\}$"
)


def gh_text(args: list[str], timeout: float = GH_TIMEOUT) -> tuple[bool, str]:
    """Run `gh`; returns (ok, stdout or the reason it failed)."""
    gh = shutil.which("gh")
    if gh is None:
        return False, "the GitHub CLI (gh) is not installed"
    try:
        proc = subprocess.run([gh, *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "could not run gh: %s" % exc
    if proc.returncode != 0:
        return False, ((proc.stderr or proc.stdout).strip().splitlines() or ["gh failed"])[0][:200]
    return True, proc.stdout


def is_hosted(labels: list[str]) -> bool:
    """A label set GitHub provides itself: no self-hosted label, a hosted image name."""
    low = [x.lower() for x in labels]
    return "self-hosted" not in low and any(x.startswith(HOSTED_PREFIXES) for x in low)


def runner_carries(runner_labels: list[str], needed: list[str]) -> bool:
    have = {x.lower() for x in runner_labels} | {"self-hosted"}
    return all(n.lower() in have for n in needed)


def list_online_runners(repo: str | None = None) -> tuple[list[list[str]] | None, str | None]:
    """(label lists of the online runners, None) or (None, why they cannot be listed)."""
    path = ("repos/%s/actions/runners" % repo) if repo else "repos/{owner}/{repo}/actions/runners"
    ok, text = gh_text(["api", path + "?per_page=100"])
    if not ok:
        return None, text
    try:
        data = json.loads(text or "null")
    except json.JSONDecodeError:
        return None, "gh api returned invalid JSON"
    if not isinstance(data, dict) or not isinstance(data.get("runners"), list):
        return None, "gh api returned no runner list"
    out = []
    for r in data["runners"]:
        if isinstance(r, dict) and r.get("status") == "online":
            out.append([str(x.get("name", "")) for x in r.get("labels", []) if isinstance(x, dict)])
    return out, None


def _clean(value: str) -> str:
    value = re.sub(r"\s+#.*$", "", value.strip())
    return value.strip().strip("'\"")


def parse_runs_on(text: str) -> list[tuple[str, str]]:
    """[(job id, raw runs-on)] from one workflow file, without a YAML library. The raw
    value is a scalar, a `[a, b]` flow list, a `${{ ... }}` expression, or the block list
    joined as `[a, b]`."""
    found: list[tuple[str, str]] = []
    lines = text.splitlines()
    in_jobs, job = False, "?"
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            continue
        if in_jobs and re.match(r"^\S", line) and not line.startswith("#"):
            in_jobs = False
        if not in_jobs:
            continue
        m = re.match(r"^  ([A-Za-z0-9_.-]+):\s*(#.*)?$", line)
        if m:
            job = m.group(1)
            continue
        m = re.match(r"^    runs-on:\s*(.*)$", line)
        if not m:
            continue
        rest = re.sub(r"\s+#.*$", "", m.group(1)).strip()
        if rest:
            found.append((job, rest))
            continue
        items = []
        while i < len(lines):
            n = re.match(r"^\s+-\s*(.+)$", lines[i])
            if not n:
                break
            items.append(_clean(n.group(1)))
            i += 1
        found.append((job, "[%s]" % ", ".join(items) if items else ""))
    return found


def _labels_from(value: str) -> list[str] | None:
    value = value.strip()
    if not value:
        return None
    if value.startswith("["):
        try:
            data = json.loads(value)
            return [str(x) for x in data]
        except json.JSONDecodeError:
            inner = value.strip("[]")
            return [_clean(x) for x in inner.split(",") if _clean(x)] or None
    return [_clean(value)]


def resolve_labels(raw: str, var_lookup) -> tuple[list[str] | None, str | None]:
    """(labels, note). note says what was assumed; labels None when it cannot be known."""
    m = _EXPR.match(raw.strip())
    if m:
        name = m.group("var")
        value = var_lookup(name)
        note = None
        if value is None:
            value = (m.group("default") or "").replace("''", "'") or None
            note = "variable %s not read; its default was assumed" % name
        if value is None:
            return None, "variable %s is not set and has no default" % name
        if m.group("json"):
            try:
                data = json.loads(value)
            except json.JSONDecodeError:
                return None, "variable %s is not JSON" % name
            return ([str(x) for x in data] if isinstance(data, list) else [str(data)]), note
        return [value], note
    if "${{" in raw:
        return None, "expression %s cannot be resolved" % raw.strip()
    return _labels_from(raw), None


def make_var_lookup(repo: str | None):
    cache: dict[str, str | None] = {}

    def lookup(name: str) -> str | None:
        if name not in cache:
            args = ["variable", "get", name] + (["--repo", repo] if repo else [])
            ok, text = gh_text(args)
            cache[name] = text.strip() if ok and text.strip() else None
        return cache[name]

    return lookup


def workflow_requirements(root: Path, var_lookup) -> tuple[list[dict], list[str]]:
    """[{file, job, labels}] and notes (what was assumed or could not be resolved)."""
    reqs, notes = [], []
    wf_dir = root / ".github" / "workflows"
    files = sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))) if wf_dir.is_dir() else []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for job, raw in parse_runs_on(text):
            labels, note = resolve_labels(raw, var_lookup)
            if note and note not in notes:
                notes.append(note)
            if labels:
                reqs.append({"file": f.name, "job": job, "labels": labels})
    return reqs, notes


def check(root: Path, repo: str | None = None, var_lookup=None, runners_fn=None) -> dict:
    """{status: ok|warn|skipped, warnings, notes, reason, needs}. Never raises."""
    var_lookup = var_lookup or make_var_lookup(repo)
    runners_fn = runners_fn or (lambda: list_online_runners(repo))
    reqs, notes = workflow_requirements(root, var_lookup)
    result = {"status": "ok", "warnings": [], "notes": notes, "reason": None, "needs": []}
    if not reqs:
        result["notes"] = notes + ["no workflow jobs with a runs-on label found"]
        return result
    selfhosted: dict[tuple, list[str]] = {}
    for r in reqs:
        if not is_hosted(r["labels"]):
            selfhosted.setdefault(tuple(r["labels"]), []).append("%s:%s" % (r["file"], r["job"]))
    result["needs"] = [{"labels": list(k), "jobs": v} for k, v in selfhosted.items()]
    if not selfhosted:
        return result
    runners, why = runners_fn()
    if runners is None:
        result["status"] = "skipped"
        result["reason"] = "the online runners could not be listed (%s); listing them needs admin rights" % why
        return result
    for labels, jobs in selfhosted.items():
        if not any(runner_carries(r, list(labels)) for r in runners):
            result["warnings"].append(
                "no online runner carries [%s] (needed by %s)%s" % (
                    ", ".join(labels), ", ".join(jobs[:4]) + (" ..." if len(jobs) > 4 else ""),
                    "" if runners else "; no runner is online at all"))
    if result["warnings"]:
        result["status"] = "warn"
    return result


def report(res: dict, prefix: str = "runner health") -> None:
    """Print a check() result: warnings, the skip reason, or one OK line."""
    for note in res["notes"]:
        print("%s: note: %s" % (prefix, note))
    if res["status"] == "skipped":
        print("%s: check skipped: %s" % (prefix, res["reason"]))
    elif res["status"] == "warn":
        for w in res["warnings"]:
            print("%s: WARNING: %s. The ready PR's CI would queue until one is online." % (prefix, w))
    else:
        print("%s: ok (every job's labels are GitHub-hosted or carried by an online runner)" % prefix)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", help="OWNER/NAME (default: the current repository)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    args = ap.parse_args(argv)
    res = check(Path.cwd(), args.repo)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        report(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
