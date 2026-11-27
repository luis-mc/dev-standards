#!/usr/bin/env python3
"""Replay pull requests through the carry-forward plan and count the saved job-minutes (DS287, R5.93).

    carry_replay.py --repo OWNER/REPO --prs N,N [--workflow FILE.yml] [--json]

Read-only. It reads the recorded runs with `gh api` and the git history of the pull requests from a temporary
clone (`git fetch origin pull/N/head`); it changes nothing in the repository or on GitHub. For each head of each
pull request, oldest first, it prints:

  ran      the jobs that ran on that head (not skipped)
  planned  the jobs carry_plan.py would have run, given only the earlier heads
  saved    the job-minutes of the jobs that ran but the plan would have carried (job started to completed)

and a total. The first head of a pull request runs everything. Without --workflow every workflow of the
repository that has pull_request runs on the pull request is replayed. The area map and the workflow file are
read at each head from the repository itself, so it works for any repository. Python 3.11, standard library only.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import area_select as AS  # noqa: E402
import carry_plan as CP  # noqa: E402

MAP_PATH = "scripts/delivery/ci-areas.json"


def _ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def job_minutes(api_jobs: list, defs: dict) -> dict[str, float]:
    """{job key: minutes} of the jobs that really ran (started and completed)."""
    out: dict[str, float] = {}
    for j in api_jobs:
        if not isinstance(j, dict) or j.get("conclusion") in CP.SKIPPED:
            continue
        key = CP.api_job_key(j.get("name", ""), defs)
        a, b = _ts(j.get("started_at")), _ts(j.get("completed_at"))
        if key is None:
            continue
        out[key] = out.get(key, 0.0) + (max((b - a).total_seconds(), 0.0) / 60 if a and b else 0.0)
    return out


def replay_workflow(runs: list, read_file, changed_since, workflow_path: str) -> list[dict]:
    """runs: completed runs of one workflow on one PR, each with its "jobs" recorded.
    read_file(sha, path) -> text or None. changed_since(head, proof) -> paths (may raise CP.Undecided).
    Returns one row per head, oldest first."""
    heads = CP.group_heads(runs, "")
    heads.reverse()
    by_id = {r["id"]: r.get("jobs", []) for r in runs}
    rows = []
    for i, head in enumerate(heads):
        sha = head["sha"]
        text = read_file(sha, workflow_path)
        defs = AS.parse_workflow_jobs(text or "")
        keys = list(defs)
        ran_min: dict[str, float] = {}
        for run in head["runs"]:
            for k, m in job_minutes(by_id.get(run["id"], []), defs).items():
                ran_min[k] = ran_min.get(k, 0.0) + m
        ran = [k for k in keys if k in ran_min]
        earlier = [r for h in heads[:i] for r in h["runs"]]
        cmap_text = read_file(sha, MAP_PATH)
        try:
            cmap = json.loads(cmap_text) if cmap_text else None
            if not isinstance(cmap, dict) or not isinstance(cmap.get("areas"), dict):
                cmap = None
        except ValueError:
            cmap = None
        if not keys or cmap is None:
            res = CP.everything(keys, "no workflow or area map at this head: every job runs")
        else:
            res = CP.plan(keys, defs, earlier, sha, lambda rid: by_id.get(rid, []),
                          lambda proof: changed_since(sha, proof), cmap, text, workflow_path)
        saved = sum(ran_min[k] for k in ran if k not in res["run"])
        rows.append({"head": sha, "ran": ran, "planned": res["run"], "carried": sorted(res["carried"]),
                     "saved_minutes": round(saved, 2), "reason": res["reason"]})
    return rows


def total(rows: list[dict]) -> float:
    return round(sum(r["saved_minutes"] for r in rows), 2)


# ---------------------------------------------------------------- live data (gh + git)

def collect_runs(repo: str, workflow: str, pr: int, head_ref: str) -> list:
    runs = CP.pr_runs(repo, workflow, pr, head_ref)
    for r in runs:
        r["jobs"] = CP.jobs_of_run(repo, r["id"])
    return runs


def replay_pr(repo: str, pr: int, workflow: str | None, tmp: str, map_ref: str = "") -> dict:
    info = CP.gh_api(f"repos/{repo}/pulls/{pr}")
    head_ref, base = info["head"]["ref"], info["base"]["ref"]
    if workflow:
        flows = [workflow]
    else:
        data = CP.gh_api(f"repos/{repo}/actions/workflows", per_page="100")
        flows = [Path(w["path"]).name for w in data.get("workflows", []) if w.get("state") == "active"]
    clone = str(Path(tmp) / f"pr{pr}")
    url = f"https://github.com/{repo}.git"
    CP.git(tmp, "init", "-q", clone)
    CP.git(clone, "remote", "add", "origin", url)
    CP.git(clone, "fetch", "-q", "origin", f"{base}:refs/remotes/origin/{base}", f"pull/{pr}/head:refs/pr/{pr}")

    def read_file(sha, path):
        if map_ref and path == MAP_PATH:  # --map-ref: today's map for every head (a PR older than its map)
            sha = f"origin/{base}" if map_ref == "base" else map_ref
        try:
            CP.ensure_commit(clone, sha)
            return CP.git(clone, "show", f"{sha}:{path}")
        except CP.Undecided:
            return None

    def changed(head, proof):
        CP.ensure_commit(clone, head)  # an old head is not in pull/N/head: fetch it by sha
        return CP.changed_paths_since(clone, f"origin/{base}", head, proof)

    out = {"pr": pr, "workflows": {}}
    for wf in flows:
        try:
            runs = collect_runs(repo, wf, pr, head_ref)
        except CP.Undecided:
            continue
        if runs:
            out["workflows"][wf] = replay_workflow(runs, read_file, changed, f".github/workflows/{wf}")
    return out


def render(results: list[dict]) -> str:
    lines = []
    grand = 0.0
    for res in results:
        for wf, rows in res["workflows"].items():
            lines.append(f"PR #{res['pr']} {wf}")
            for r in rows:
                lines.append(f"  {r['head'][:10]}  ran: {','.join(r['ran']) or '-'}  planned: {','.join(r['planned']) or '-'}"
                             f"  saved: {r['saved_minutes']} job-min")
            grand += total(rows)
    lines.append(f"total saved: {round(grand, 2)} job-minutes")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="what the carry-forward plan would have saved on these pull requests")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--prs", required=True, help="comma list of pull request numbers")
    ap.add_argument("--workflow", default="")
    ap.add_argument("--map-ref", default="", help="read the area map from this ref for every head ('base' = the base branch tip)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        prs = [int(x) for x in a.prs.split(",") if x.strip()]
    except ValueError:
        print("carry_replay: --prs must be numbers", file=sys.stderr)
        return 2
    tmp = tempfile.mkdtemp(prefix="carry-replay-")
    try:
        results = [replay_pr(a.repo, n, a.workflow or None, tmp, a.map_ref) for n in prs]
    except (CP.Undecided, KeyError, TypeError) as exc:
        print(f"carry_replay: {exc}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    grand = round(sum(total(r) for res in results for r in res["workflows"].values()), 2)
    if a.json:
        print(json.dumps({"prs": results, "total_saved_minutes": grand}, indent=1))
    else:
        print(render(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
