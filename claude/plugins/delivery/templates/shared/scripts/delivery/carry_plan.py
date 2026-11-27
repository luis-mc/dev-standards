#!/usr/bin/env python3
"""Carry-forward plan for a pull request's CI run (DS287, DELIVERYSPEC R5.88, R5.89).

    carry_plan.py --repo OWNER/REPO --workflow FILE.yml --pr N --sha HEAD [--map scripts/delivery/ci-areas.json]
                  [--workflow-path .github/workflows/FILE.yml] [--base-ref BRANCH] [--github-output] [--json]

Run in the plan job of a workflow on a `pull_request` event, in a checkout with full history. For each job of the
workflow it looks for the job's proof head: the newest earlier head of this pull request where the job's newest
completed run (of this workflow) ended `success`. A job skipped by a carry is not a proof.

A job runs when it has no proof head, or when a change since the proof head reaches it (area_select.py reads the
`areas`, `always_jobs` and valves of the map). Every other job is carried: it is skipped and the plan names the run
that proved it. The first run of a pull request (no earlier completed run) runs every job (R5.89).

Changed paths since a proof head: the commits of merge-base(base, HEAD)..HEAD that the proof head does not hold.
A commit whose `git patch-id --stable` is in the proof head's range counts as proven (a rebase). A merge commit
counts with the paths it brings (diff to its first parent).

Any error, or a proof head that cannot be fetched: that job runs (or every job, with the reason).

With --push (R5.95), on a push to the default branch: SHA is the merge commit of a pull request. Each job's proof
head is searched among that pull request's heads; the changed paths are the tree diff from the proof head to the
merge commit. Same tree: every job is carried. A job named in --always (release, publish, smoke) always runs. A
push that no merged pull request made runs every job.

Outputs (lines to $GITHUB_OUTPUT with --github-output; JSON with --json):
  run=a,b               the jobs to run
  run_<job>=true|false  one per job
  carried=<json>        {job: {"sha", "run_url"}} of the carried jobs, compact
  reason=...            one line
Always exits 0. Python 3.11, standard library only; `gh` and `git` are the external tools.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import area_select as AS  # noqa: E402

DEFAULT_MAP = "scripts/delivery/ci-areas.json"
SKIPPED = {"skipped", None, ""}
MAX_HEADS = 12


class Undecided(Exception):
    """A step failed; the caller runs the job (or everything)."""


class _Done(Exception):
    """Carries a finished push plan out of the try block."""

    def __init__(self, res: dict):
        super().__init__("done")
        self.res = res


# ---------------------------------------------------------------- job names

def _name_regex(name: str):
    parts = re.split(r"\$\{\{.*?\}\}", name)
    return re.compile("^" + ".+".join(re.escape(p.strip().lower()) for p in parts) + "$")


def api_job_key(api_name: str, defs: dict[str, dict]) -> str | None:
    """Map an API job name to a workflow job key; a matrix leg "name (3)" and a reusable "caller / inner" collapse."""
    raw = (api_name or "").strip().lower()
    cands = [raw, re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()]
    if " / " in raw:
        cands.append(raw.split(" / ", 1)[0].strip())
    for cand in cands:
        for key in defs:
            if cand == key.lower():
                return key
        for key, d in defs.items():
            if d.get("name") and _name_regex(d["name"]).match(cand):
                return key
    return None


def job_conclusions(api_jobs: list, defs: dict[str, dict]) -> dict[str, list]:
    out: dict[str, list] = {}
    for j in api_jobs:
        if isinstance(j, dict):
            key = api_job_key(j.get("name", ""), defs)
            if key:
                out.setdefault(key, []).append(j.get("conclusion"))
    return out


def run_verdict(conclusions: list | None) -> str | None:
    """'success' | 'fail' | None (skipped or absent: no information)."""
    real = [c for c in conclusions or [] if c not in SKIPPED]
    if not real:
        return None
    return "success" if all(c == "success" for c in real) and len(real) == len(conclusions) else "fail"


# ---------------------------------------------------------------- proof heads

def group_heads(runs: list, head_sha: str) -> list[dict]:
    """Earlier heads, newest first: [{"sha", "runs": [run, ...newest first]}] of completed runs."""
    by: dict[str, list] = {}
    for r in runs:
        if isinstance(r, dict) and r.get("head_sha") and r["head_sha"] != head_sha and r.get("status", "completed") == "completed":
            by.setdefault(r["head_sha"], []).append(r)
    heads = []
    for sha, rs in by.items():
        rs.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
        heads.append({"sha": sha, "runs": rs})
    heads.sort(key=lambda h: str(h["runs"][0].get("created_at", "")), reverse=True)
    return heads


def find_proofs(heads: list[dict], job_keys: list[str], defs: dict, fetch_jobs) -> dict[str, dict]:
    """{job: {"sha", "run_url", "run_id"}}. Looks at heads newest first; fetch_jobs(run_id) -> API jobs."""
    proofs: dict[str, dict] = {}
    for head in heads[:MAX_HEADS]:
        pending = [k for k in job_keys if k not in proofs]
        if not pending:
            break
        decided: set[str] = set()
        for run in head["runs"]:
            conc = job_conclusions(fetch_jobs(run.get("id")), defs)
            for k in pending:
                if k in decided:
                    continue
                v = run_verdict(conc.get(k))
                if v is None:
                    continue
                decided.add(k)
                if v == "success":
                    proofs[k] = {"sha": head["sha"], "run_url": run.get("html_url", ""), "run_id": run.get("id")}
    return proofs


# ---------------------------------------------------------------- decision (pure)

def decide(job_keys: list[str], proofs: dict, changed_since, cmap: dict, workflow_text: str | None,
           workflow_path: str | None) -> dict:
    """changed_since(sha) -> list of paths, or raises Undecided. Returns {run, carried, reason}."""
    cache: dict[str, dict | None] = {}
    notes: list[str] = []

    def sel(sha: str):
        if sha not in cache:
            try:
                paths = changed_since(sha)
            except Undecided as exc:
                notes.append(f"{sha[:10]}: {exc}")
                cache[sha] = None
                return None
            cache[sha] = {"none": True, "jobs": {}} if not paths else AS.select(paths, cmap, False, workflow_text, workflow_path)
        return cache[sha]

    run: list[str] = []
    carried: dict[str, dict] = {}
    for k in job_keys:
        pf = proofs.get(k)
        if not pf:
            run.append(k)
            continue
        res = sel(pf["sha"])
        if res is None:
            run.append(k)
        elif res.get("none"):
            carried[k] = {"sha": pf["sha"], "run_url": pf.get("run_url", "")}
        elif res["jobs"].get(k, True):  # a job the map does not list is never carried
            run.append(k)
        else:
            carried[k] = {"sha": pf["sha"], "run_url": pf.get("run_url", "")}
    reason = f"run {len(run)} of {len(job_keys)} jobs, carried {len(carried)}"
    if notes:
        reason += "; " + "; ".join(notes)
    return {"run": run, "carried": carried, "reason": reason}


def everything(job_keys: list[str], reason: str) -> dict:
    return {"run": list(job_keys), "carried": {}, "reason": reason}


def plan(job_keys: list[str], defs: dict, runs: list, head_sha: str, fetch_jobs, changed_since, cmap: dict,
         workflow_text: str | None, workflow_path: str | None) -> dict:
    """The whole plan on plain data: runs = completed pull_request runs of this workflow on the PR."""
    heads = group_heads(runs, head_sha)
    if not heads:
        return everything(job_keys, "first run of this pull request: every job runs")
    proofs = find_proofs(heads, job_keys, defs, fetch_jobs)
    return decide(job_keys, proofs, changed_since, cmap, workflow_text, workflow_path)


def push_plan(job_keys: list[str], defs: dict, runs: list, merge_sha: str, fetch_jobs, changed_since, cmap: dict,
              workflow_text: str | None, workflow_path: str | None, always: list[str]) -> dict:
    """R5.95: the plan for a push of a merge commit; runs = completed pull_request runs of the merged PR."""
    heads = group_heads(runs, merge_sha)
    if not heads:
        res = everything(job_keys, "no pull request run proves this merge: every job runs")
    else:
        proofs = find_proofs(heads, job_keys, defs, fetch_jobs)
        res = decide(job_keys, proofs, changed_since, cmap, workflow_text, workflow_path)
    for k in always:
        if k in res["carried"]:
            del res["carried"][k]
        if k in job_keys and k not in res["run"]:
            res["run"].append(k)
    res["run"] = [k for k in job_keys if k in res["run"]]
    res["reason"] = "push of a merge: " + res["reason"]
    return res


def tree_diff(repo: str, proof: str, sha: str) -> list[str]:
    """R5.95: paths whose content differs between the proof head and the merge commit."""
    ensure_commit(repo, proof)
    out = git(repo, "diff", "--name-only", "--no-renames", "-z", proof, sha)
    return [p for p in out.split("\0") if p]


def merged_pr(repo: str, sha: str) -> dict | None:
    data = gh_api(f"repos/{repo}/commits/{sha}/pulls")
    for pr in data if isinstance(data, list) else []:
        if isinstance(pr, dict) and pr.get("merge_commit_sha") == sha and pr.get("merged_at"):
            return pr
    return None


# ---------------------------------------------------------------- git

def git(repo: str, *args: str, input_text: str | None = None) -> str:
    try:
        p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", input=input_text, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Undecided(f"git {args[0]}: {exc}") from exc
    if p.returncode != 0:
        raise Undecided(f"git {' '.join(args[:2])} failed: {(p.stderr or p.stdout).strip()[:200]}")
    return p.stdout


def patch_ids(repo: str, rev_range: list[str]) -> dict[str, str]:
    """{commit: patch-id} of the non-merge commits of the range."""
    log = git(repo, "log", "--no-merges", "-p", "--no-renames", "--format=commit %H", *rev_range)
    if not log.strip():
        return {}
    out = git(repo, "patch-id", "--stable", input_text=log)
    return {c: pid for pid, c in (ln.split() for ln in out.splitlines() if len(ln.split()) == 2)}


def ensure_commit(repo: str, sha: str) -> None:
    try:
        git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
    except Undecided:
        try:
            git(repo, "fetch", "--quiet", "origin", sha)
            git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
        except Undecided as exc:
            raise Undecided(f"proof head {sha[:10]} cannot be fetched") from exc


def changed_paths_since(repo: str, base_ref: str, head: str, proof: str) -> list[str]:
    """Paths of the commits of merge-base(base, head)..head that the proof head does not hold."""
    ensure_commit(repo, proof)
    mb = git(repo, "merge-base", base_ref, head).strip()
    new = [c for c in git(repo, "rev-list", "--reverse", f"{mb}..{head}", f"^{proof}").split()]
    if not new:
        return []
    proven = set(patch_ids(repo, [f"{mb}..{proof}"]).values())
    ids = patch_ids(repo, [f"{mb}..{head}", f"^{proof}"])
    paths: list[str] = []
    for c in new:
        if c in ids and ids[c] in proven:
            continue
        parents = git(repo, "rev-list", "--parents", "-n", "1", c).split()[1:]
        if len(parents) > 1:
            out = git(repo, "diff", "--name-only", "--no-renames", "-z", f"{c}^1", c)
        else:
            out = git(repo, "diff-tree", "--root", "--no-commit-id", "--name-only", "--no-renames", "-r", "-z", c)
        paths += [p for p in out.split("\0") if p and p not in paths]
    return paths


# ---------------------------------------------------------------- gh

def run_cmd(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Undecided(f"could not run {cmd[0]}: {exc}") from exc
    if p.returncode != 0:
        raise Undecided(f"{' '.join(cmd[:3])} failed ({p.returncode}): {(p.stderr or p.stdout).strip()[:300]}")
    return p.stdout.strip()


def gh_api(path: str, **query):
    cmd = ["gh", "api", "--method", "GET", "-H", "Accept: application/vnd.github+json", path]
    for k, v in query.items():
        cmd += ["-f", f"{k}={v}"]
    try:
        return json.loads(run_cmd(cmd) or "null")
    except json.JSONDecodeError as exc:
        raise Undecided(f"gh api {path}: invalid JSON: {exc}") from exc


def pr_runs(repo: str, workflow: str, pr: int, head_ref: str) -> list:
    data = gh_api(f"repos/{repo}/actions/workflows/{workflow}/runs", branch=head_ref, event="pull_request",
                  status="completed", per_page="100")
    runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
    out = []
    for r in runs:
        nums = [p.get("number") for p in r.get("pull_requests") or [] if isinstance(p, dict)]
        if not nums or pr in nums:
            out.append(r)
    return out


def jobs_of_run(repo: str, run_id) -> list:
    data = gh_api(f"repos/{repo}/actions/runs/{run_id}/jobs", per_page="100")
    return data.get("jobs", []) if isinstance(data, dict) else []


# ---------------------------------------------------------------- output

def lines(job_keys: list[str], res: dict) -> list[str]:
    out = [f"run={','.join(res['run'])}"]
    out += [f"run_{k}={'true' if k in res['run'] else 'false'}" for k in job_keys]
    out.append(f"carried={json.dumps(res['carried'], separators=(',', ':'), sort_keys=True)}")
    out.append("reason=" + " ".join(res["reason"].split()))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="which jobs of this workflow must run on this pull request head")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--pr", type=int, default=0)
    ap.add_argument("--push", action="store_true", help="a push of a merge commit to the default branch (R5.95)")
    ap.add_argument("--always", default="", help="comma list of jobs that run on every push (release, publish, smoke)")
    ap.add_argument("--sha", default=os.environ.get("GITHUB_SHA", "HEAD"))
    ap.add_argument("--map", default=DEFAULT_MAP)
    ap.add_argument("--workflow-path", default="")
    ap.add_argument("--base-ref", default="", help="the base branch (default: from the pull request)")
    ap.add_argument("--github-output", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    wf_path = a.workflow_path or f".github/workflows/{a.workflow}"
    job_keys: list[str] = []
    try:
        text = Path(wf_path).read_text(encoding="utf-8")
        defs = AS.parse_workflow_jobs(text)
        job_keys = list(defs)
        if not job_keys:
            raise Undecided(f"no jobs found in {wf_path}")
    except (OSError, Undecided) as exc:
        res = everything(job_keys, f"cannot read the workflow, nothing to carry: {exc}")
        defs, text = {}, None
    else:
        try:
            cmap = AS.load_map(Path(a.map))
            sha = git(".", "rev-parse", a.sha).strip()
            if a.push:
                mpr = merged_pr(a.repo, sha)
                always = [j for j in a.always.split(",") if j]
                if not mpr:
                    raise Undecided("no merged pull request made this push")
                runs = pr_runs(a.repo, a.workflow, int(mpr["number"]), mpr["head"]["ref"])
                res = push_plan(job_keys, defs, runs, sha, lambda rid: jobs_of_run(a.repo, rid),
                                lambda proof: tree_diff(".", proof, sha), cmap, text, wf_path, always)
                raise _Done(res)
            if not a.pr:
                raise Undecided("--pr is required without --push")
            pr = gh_api(f"repos/{a.repo}/pulls/{a.pr}")
            head_ref = pr["head"]["ref"]
            base = a.base_ref or pr["base"]["ref"]
            base_ref = f"origin/{base}"
            runs = pr_runs(a.repo, a.workflow, a.pr, head_ref)
            res = plan(job_keys, defs, runs, sha, lambda rid: jobs_of_run(a.repo, rid),
                       lambda proof: changed_paths_since(".", base_ref, sha, proof), cmap, text, wf_path)
        except _Done as done:
            res = done.res
        except (Undecided, OSError, ValueError, KeyError, TypeError) as exc:
            res = everything(job_keys, f"could not plan, every job runs: {exc}")
        except Exception as exc:  # fail open
            res = everything(job_keys, f"unexpected {type(exc).__name__}, every job runs: {exc}")
    if a.json:
        print(json.dumps({"run": res["run"], "jobs": {k: k in res["run"] for k in job_keys},
                          "carried": res["carried"], "reason": res["reason"]}))
    else:
        print("carry_plan: " + " ".join(lines(job_keys, res)))
    target = os.environ.get("GITHUB_OUTPUT")
    if a.github_output and target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines(job_keys, res)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
