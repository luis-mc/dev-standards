#!/usr/bin/env python3
"""Decide whether a default-branch push may skip the CI suite (STACKSPEC 13.1).

A push to the default branch must not repeat a suite that already passed. When
the pushed commit's tree is identical to the tree of a pull-request head whose
run of the same workflow passed, the suite has already vouched for exactly this
content, and the jobs can be skipped. The comparison is by tree, so a merge
that changed anything runs the suite, and failing to decide runs it too.

Reads GITHUB_SHA, GITHUB_REPOSITORY and GITHUB_WORKFLOW_REF (for example
`owner/repo/.github/workflows/ci.yml@refs/heads/main`). Uses `gh api` to find
the pull request(s) the commit belongs to and a successful `pull_request` run of
the same workflow file for each head, then compares `git rev-parse <sha>^{tree}`
with `<head>^{tree}`.

Writes `skip=true|false` and `reason=...` to $GITHUB_OUTPUT (appended; printed
when it is unset). On any error the answer is `skip=false` with the error as the
reason. Always exits 0: failing open means running the suite.

Python 3.11+, standard library only; `gh` and `git` are the external tools.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

FAILED_JOB = {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}


class Undecided(Exception):
    """Something prevented a decision; the suite runs."""


def run(cmd: list[str]) -> str:
    # The resolved path, so Windows finds gh whatever its extension.
    cmd = [shutil.which(cmd[0]) or cmd[0], *cmd[1:]]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Undecided(f"could not run {cmd[0]}: {exc}") from exc
    if proc.returncode != 0:
        raise Undecided(f"{' '.join(cmd[:3])} failed ({proc.returncode}): "
                        f"{(proc.stderr or proc.stdout).strip()[:300]}")
    return proc.stdout.strip()


def gh_api(path: str, **query: str) -> object:
    """GET `path` with query parameters passed as `-f` fields (what `gh api` turns into
    `?k=v&...` for a GET), so no argument carries a shell metacharacter such as `&`."""
    cmd = ["gh", "api", "--method", "GET", "-H", "Accept: application/vnd.github+json", path]
    for key, value in query.items():
        cmd += ["-f", f"{key}={value}"]
    out = run(cmd)
    try:
        return json.loads(out or "null")
    except json.JSONDecodeError as exc:
        raise Undecided(f"gh api {path} returned invalid JSON: {exc}") from exc


def workflow_path(ref: str, repo: str) -> str:
    """`owner/repo/.github/workflows/ci.yml@refs/heads/main` -> `.github/workflows/ci.yml`."""
    path = ref.split("@", 1)[0]
    prefix = repo + "/"
    if not path.startswith(prefix):
        raise Undecided(f"GITHUB_WORKFLOW_REF {ref!r} does not start with {prefix!r}")
    return path[len(prefix):]


def tree_of(commit: str) -> str:
    return run(["git", "rev-parse", f"{commit}^{{tree}}"])


def ensure_commit(sha: str, number: object) -> None:
    probe = ["git", "cat-file", "-e", f"{sha}^{{commit}}"]
    if subprocess.run(probe, capture_output=True).returncode == 0:
        return
    try:
        run(["git", "fetch", "--no-tags", "origin", sha])
    except Undecided:
        if not number:
            raise
        run(["git", "fetch", "--no-tags", "origin", f"refs/pull/{number}/head"])


def run_really_passed(repo: str, run_id: object) -> bool:
    """A run whose jobs were all skipped (a draft) reports success; require a job that ran."""
    data = gh_api(f"repos/{repo}/actions/runs/{run_id}/jobs", per_page="100")
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    conclusions = [j.get("conclusion") for j in jobs if isinstance(j, dict)]
    return "success" in conclusions and not (set(conclusions) & FAILED_JOB)


def decide(env: dict[str, str]) -> tuple[bool, str]:
    sha = env.get("GITHUB_SHA", "")
    repo = env.get("GITHUB_REPOSITORY", "")
    wf_ref = env.get("GITHUB_WORKFLOW_REF", "")
    missing = [n for n, v in (("GITHUB_SHA", sha), ("GITHUB_REPOSITORY", repo),
                              ("GITHUB_WORKFLOW_REF", wf_ref)) if not v]
    if missing:
        raise Undecided("missing environment: " + ", ".join(missing))
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise Undecided(f"GITHUB_SHA {sha!r} is not a full sha")
    wf_path = workflow_path(wf_ref, repo)

    pulls = gh_api(f"repos/{repo}/commits/{sha}/pulls")
    if not isinstance(pulls, list) or not pulls:
        return False, f"no pull request is associated with {sha[:10]}"

    sha_tree = tree_of(sha)
    notes: list[str] = []
    for pr in pulls:
        number = pr.get("number")
        head = (pr.get("head") or {}).get("sha", "")
        if not re.fullmatch(r"[0-9a-f]{40}", head or ""):
            notes.append(f"#{number}: no head sha")
            continue
        runs = gh_api(f"repos/{repo}/actions/runs",
                      head_sha=head, event="pull_request", status="success")
        candidates = [r for r in (runs.get("workflow_runs", []) if isinstance(runs, dict) else [])
                      if isinstance(r, dict)
                      and str(r.get("path", "")).split("@", 1)[0] == wf_path
                      and r.get("head_sha", head) == head]
        if not candidates:
            notes.append(f"#{number}: no successful pull_request run of {wf_path} "
                         f"for {head[:10]}")
            continue
        ensure_commit(head, number)
        head_tree = tree_of(head)
        if head_tree != sha_tree:
            notes.append(f"#{number}: tree of {head[:10]} differs from tree of {sha[:10]}")
            continue
        for cand in candidates:
            if run_really_passed(repo, cand.get("id")):
                return True, (f"tree {sha_tree[:10]} already passed {wf_path} in run "
                              f"{cand.get('id')} on #{number} ({head[:10]})")
        notes.append(f"#{number}: the matching run had no job that passed")
    return False, "; ".join(notes) or "no matching pull request run"


def emit(skip: bool, reason: str) -> None:
    reason = " ".join(reason.split())  # one line: $GITHUB_OUTPUT is line oriented
    line = f"skip={'true' if skip else 'false'}\nreason={reason}\n"
    print(f"ci_skip_check: skip={'true' if skip else 'false'} ({reason})")
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as exc:
        print(f"ci_skip_check: could not write {target}: {exc}", file=sys.stderr)


def main() -> int:
    try:
        skip, reason = decide(dict(os.environ))
    except Undecided as exc:
        skip, reason = False, f"could not decide, running the suite: {exc}"
    except Exception as exc:  # fail open on anything unexpected
        skip, reason = False, f"unexpected {type(exc).__name__}, running the suite: {exc}"
    emit(skip, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
