#!/usr/bin/env python3
"""Workflow helper for the narrowed rerun of a test job (DS287, R5.92).

    rerun_step.py lookup --repo R --workflow F --pr N --sha HEAD --job-name NAME --report-name ART [--out DIR]
    rerun_step.py mode DECISION.json
    rerun_step.py exec --decision DECISION.json --prefix CMD [--then-prefix CMD] [--then-suffix ARGS] [--tee FILE]

`lookup` finds the newest completed run of this workflow on this pull request whose head is not `--sha`, where the
job `--job-name` was not skipped. It prints `prev_conclusion=`, `prev_sha=` and `report=` lines (to $GITHUB_OUTPUT when
set) and writes the files changed since that head to DIR/changed.txt. It downloads the artifact `--report-name`
when the run has one. Any error prints a warning and gives empty values: the job runs its normal command.
`mode` prints `mode=whole|current|narrow` from the rerun_tests.py answer (`current` when it cannot be read).
`exec` runs step 1 (`invocations`), then each `then` invocation when step 1 passed. Fails if either fails.
Python 3.8+ for exec and mode; lookup uses carry_plan.py helpers.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))


def emit(pairs):
    text = "".join(f"{k}={v}\n" for k, v in pairs)
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text)
    print(text, end="")


def lookup(a):
    import carry_plan as CP
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        runs = CP.pr_runs(a.repo, a.workflow, a.pr, CP.gh_api(f"repos/{a.repo}/pulls/{a.pr}")["head"]["ref"])
        runs = sorted((r for r in runs if r.get("head_sha") != a.sha), key=lambda r: r.get("created_at") or "", reverse=True)
        for run in runs[:CP.MAX_HEADS]:
            jobs = [j for j in CP.jobs_of_run(a.repo, run["id"])
                    if (j.get("name") or "") == a.job_name or (j.get("name") or "").startswith(a.job_name + " (")]
            jobs = [j for j in jobs if j.get("conclusion") not in CP.SKIPPED]
            if not jobs:
                continue
            conclusion = "failure" if any(j["conclusion"] == "failure" for j in jobs) else jobs[0]["conclusion"]
            sha = run["head_sha"]
            CP.run_cmd(["git", "fetch", "--no-tags", "--depth=1", "origin", sha]) if _missing(sha) else None
            files = CP.run_cmd(["git", "diff", "--name-only", sha, a.sha])
            (out / "changed.txt").write_text(files + "\n", encoding="utf-8")
            report = ""
            try:
                arts = CP.gh_api(f"repos/{a.repo}/actions/runs/{run['id']}/artifacts", per_page="100")
                if any(x.get("name") == a.report_name and not x.get("expired") for x in arts.get("artifacts", [])):
                    d = out / "report"
                    CP.run_cmd(["gh", "run", "download", str(run["id"]), "-R", a.repo, "-n", a.report_name, "-D", str(d)])
                    found = sorted(p for p in d.rglob("*") if p.is_file())
                    report = str(found[0]) if found else ""
            except CP.Undecided as exc:
                print(f"::warning::rerun: no report ({exc})")
            emit([("prev_conclusion", conclusion), ("prev_sha", sha), ("report", report)])
            return 0
    except Exception as exc:  # any error: the normal command
        print(f"::warning::rerun lookup failed, the normal test command runs: {exc}")
    emit([("prev_conclusion", ""), ("prev_sha", ""), ("report", "")])
    return 0


def _missing(sha):
    return subprocess.run(["git", "cat-file", "-e", sha + "^{commit}"], capture_output=True).returncode != 0


def mode(path):
    try:
        m = json.loads(Path(path).read_text(encoding="utf-8")).get("mode")
        m = m if m in ("whole", "current", "narrow") else "current"
    except (OSError, ValueError, AttributeError):
        print("::warning::rerun answer unreadable, the normal test command runs")
        m = "current"
    emit([("mode", m)])
    return 0


def run_one(prefix, args, suffix, tee):
    cmd = shlex.split(prefix) + [str(x) for x in args] + shlex.split(suffix)
    print("+ " + " ".join(cmd), flush=True)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    fh = open(tee, "ab") if tee else None
    for chunk in iter(lambda: p.stdout.read(8192), b""):
        sys.stdout.buffer.write(chunk)
        sys.stdout.flush()
        if fh:
            fh.write(chunk)
    if fh:
        fh.close()
    return p.wait()


def execute(a):
    res = json.loads(Path(a.decision).read_text(encoding="utf-8"))
    if a.tee:
        Path(a.tee).parent.mkdir(parents=True, exist_ok=True)
        Path(a.tee).write_bytes(b"")
    bad = 0
    for inv in res.get("invocations") or []:
        bad |= run_one(a.prefix, inv, a.suffix, a.tee) != 0
    if bad:
        print("::error::the failed tests still fail; the affected packages were not run")
        return 1
    for inv in res.get("then") or []:
        bad |= run_one(a.then_prefix or a.prefix, inv, a.then_suffix, a.tee) != 0
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("lookup")
    l.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    l.add_argument("--workflow", required=True)
    l.add_argument("--pr", type=int, required=True)
    l.add_argument("--sha", required=True)
    l.add_argument("--job-name", required=True)
    l.add_argument("--report-name", required=True)
    l.add_argument("--out", default=".rerun")
    m = sub.add_parser("mode")
    m.add_argument("decision")
    e = sub.add_parser("exec")
    e.add_argument("--decision", required=True)
    e.add_argument("--prefix", required=True)
    e.add_argument("--suffix", default="")
    e.add_argument("--then-prefix", default="")
    e.add_argument("--then-suffix", default="")
    e.add_argument("--tee", default="")
    a = ap.parse_args(argv)
    return lookup(a) if a.cmd == "lookup" else mode(a.decision) if a.cmd == "mode" else execute(a)


if __name__ == "__main__":
    sys.exit(main())
