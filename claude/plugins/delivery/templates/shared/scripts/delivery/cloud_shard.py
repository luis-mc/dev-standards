#!/usr/bin/env python3
"""Run ONE CI shard in a Claude cloud session and write its result JSON (CI option c, DL15). STARTER.

    cloud_shard.py run --shard ID [--table scripts/delivery/ci-shards.json] [--sha SHA] [--out FILE]
                       [--timeout-min N] [--push --prefix ci-result --remote origin]

STARTER: this is the small, tested version of the contract in docs/features/delivery/spec.md (section 13). A
project may replace it with a runner it has proven, as long as it keeps the result JSON and the push ref below.

What it does: read the shard table, pick the shard, check that HEAD is the commit the shard must test (--sha),
run the shard's commands in order from the repository root, stop at the first failure, and write the result.
A command written `@name` is replaced by `tests.name` of the table. Nothing here talks to GitHub.

Result JSON (schema 1), written to --out (default .delivery/ci-results/<sha>/<shard>.json):
  {"schema": 1, "shard": ID, "context": CONTEXT, "os": OS, "sha": FULL_SHA, "state": "success"|"failure"|"error",
   "started": ISO8601, "finished": ISO8601, "commands": [{"command", "exit", "seconds", "tail"}], "summary": "..."}
state: success = every command exited 0; failure = a command failed or timed out; error = the shard could not run
(unknown shard, wrong OS, HEAD is not --sha, bad table).

--push publishes the result with plain git: one branch `<prefix>/<sha>/<shard id>` holding one commit with the
file `result.json`. The branch is new for each (sha, shard), so two shards never conflict. The watcher routine
reads these branches with `git ls-remote` and `git fetch`.

--records (DL20, pass_records.py): before running, compute the shard's inputs key; when a success record for it
exists (own branch and base, or the base only with --ready) the shard is skipped, the result is `success` with
`"skipped": true` and the record it relied on. After a real run a success or failure record is written. A
failed record never skips. --all ignores records. Without --records nothing changes.

Exit 0 success, 1 failure, 2 error (a result is still written when the table and the sha are known). Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

TAIL_LINES = 40
OS_NAMES = {"linux": "linux", "win32": "windows", "darwin": "macos"}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def this_os() -> str:
    return OS_NAMES.get(sys.platform, "linux" if sys.platform.startswith("linux") else sys.platform)


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def load_table(path: str):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("shards"), list):
        raise ValueError("the shard table needs a `shards` list")
    return data


def expand(command: str, tests: dict) -> str:
    m = re.fullmatch(r"@([A-Za-z0-9_.-]+)", command.strip())
    if not m:
        return command
    if m.group(1) not in tests or not isinstance(tests[m.group(1)], str):
        raise ValueError("command %s names a test that the table does not define" % command.strip())
    return tests[m.group(1)]


def run_command(command: str, cwd: str, timeout_s):
    t0 = time.monotonic()
    try:
        p = subprocess.run(command, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout_s,
                           errors="replace")
        code, out = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as exc:
        code = 124
        raw = (exc.stdout or b"")
        out = (raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw) + "\n[timed out]"
    tail = "\n".join(out.splitlines()[-TAIL_LINES:])
    return {"command": command, "exit": code, "seconds": round(time.monotonic() - t0, 1), "tail": tail}


def run_shard(table: dict, shard_id: str, cwd: str, sha: str | None, timeout_min, records=None):
    """Returns the result dict. Never raises for a bad shard: that is state error."""
    started = now_iso()
    head = git("rev-parse", "HEAD", cwd=cwd).stdout.strip()
    result = {"schema": 1, "shard": shard_id, "context": shard_id, "os": this_os(), "sha": sha or head,
              "state": "error", "started": started, "finished": started, "commands": [], "summary": ""}

    def done(state, summary):
        result.update(state=state, summary=summary, finished=now_iso())
        return result

    shard = next((s for s in table["shards"] if isinstance(s, dict) and s.get("id") == shard_id), None)
    if shard is None:
        return done("error", "no shard %r in the table" % shard_id)
    ctx = shard.get("context")
    result["context"] = ctx if isinstance(ctx, str) and ctx.strip() else shard_id
    result["os"] = shard.get("os", result["os"])
    if shard.get("os") != this_os():
        return done("error", "shard %r is for %s, this machine is %s" % (shard_id, shard.get("os"), this_os()))
    if sha and not head.startswith(sha.lower()) and head != sha:
        return done("error", "HEAD is %s, the shard must test %s" % (head[:10], sha[:10]))
    commands = shard.get("commands")
    if not isinstance(commands, list) or not commands:
        return done("error", "shard %r has no commands" % shard_id)
    tests = table.get("tests") if isinstance(table.get("tests"), dict) else {}
    if records is not None:  # pass records (DL20): the same inputs already passed -> skip, proved by the record
        key, hit, note = records.consult(table, shard_id)
        result["inputs_key"] = key
        if hit:
            result["skipped"] = True
            result["record"] = {k: hit.get(k) for k in ("key", "sha", "branch", "at")}
            return done("success", "skipped: pass record for inputs key %s (sha %s)" % (key[:12], str(hit.get("sha"))[:10]))
    limit = timeout_min * 60 if timeout_min else None
    deadline = time.monotonic() + limit if limit else None
    for raw in commands:
        try:
            cmd = expand(str(raw), tests)
        except ValueError as exc:
            return done("error", str(exc))
        remaining = None if deadline is None else max(1.0, deadline - time.monotonic())
        step = run_command(cmd, cwd, remaining)
        result["commands"].append(step)
        if step["exit"] != 0:
            return done("failure", "command failed (exit %d): %s" % (step["exit"], cmd))
    return done("success", "%d command(s) passed" % len(commands))


def write_result(result: dict, out: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2)
        f.write("\n")


def push_result(result: dict, cwd: str, prefix: str, remote: str):
    """Publish result.json as the only file of a new branch <prefix>/<sha>/<shard>. Returns (ok, message)."""
    branch = "%s/%s/%s" % (prefix, result["sha"], result["shard"])
    tmp = tempfile.mkdtemp(prefix="cloud-shard-")
    try:
        write_result(result, os.path.join(tmp, "result.json"))
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index"), GIT_AUTHOR_NAME="ci-shard",
                   GIT_AUTHOR_EMAIL="ci-shard@localhost", GIT_COMMITTER_NAME="ci-shard",
                   GIT_COMMITTER_EMAIL="ci-shard@localhost")

        def g(*a, input_=None):
            return subprocess.run(["git", *a], cwd=cwd, env=env, capture_output=True, text=True, input=input_, check=False)
        blob = g("hash-object", "-w", os.path.join(tmp, "result.json"))
        if blob.returncode:
            return False, blob.stderr.strip()
        g("update-index", "--add", "--cacheinfo", "100644,%s,result.json" % blob.stdout.strip())
        tree = g("write-tree")
        commit = g("commit-tree", tree.stdout.strip(), "-m", "ci result %s %s %s" % (result["shard"], result["sha"][:10], result["state"]))
        if commit.returncode:
            return False, commit.stderr.strip()
        pushed = g("push", remote, "%s:refs/heads/%s" % (commit.stdout.strip(), branch))
        if pushed.returncode:
            return False, pushed.stderr.strip()
        return True, branch
    finally:
        for name in os.listdir(tmp):
            try:
                os.unlink(os.path.join(tmp, name))
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cloud_shard.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["run"])
    ap.add_argument("--shard", required=True)
    ap.add_argument("--table", default="scripts/delivery/ci-shards.json")
    ap.add_argument("--sha", help="the commit the shard must test; the run is an error when HEAD differs")
    ap.add_argument("--out", help="result file (default .delivery/ci-results/<sha>/<shard>.json)")
    ap.add_argument("--timeout-min", type=float, default=None, help="all commands together; a timeout is a failure")
    ap.add_argument("--push", action="store_true", help="publish the result as a branch (see the docstring)")
    ap.add_argument("--prefix", default="ci-result")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--records", action="store_true", help="skip a shard whose inputs key has a pass record (pass_records.py)")
    ap.add_argument("--records-branch", default="ci-pass-records")
    ap.add_argument("--base", default="main", help="the base branch; its records are always read")
    ap.add_argument("--branch", default="", help="the branch under test (default: the current branch)")
    ap.add_argument("--ready", action="store_true", help="a ready pull request to --base: read only the base's records")
    ap.add_argument("--all", action="store_true", help="ignore pass records and run the shard")
    ap.add_argument("--root", default=".", help="repository root (default: the current folder)")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        table = load_table(os.path.join(root, args.table.replace("/", os.sep)))
    except (OSError, ValueError) as exc:
        print("cloud_shard: cannot read the shard table (%s)" % exc, file=sys.stderr)
        return 2
    rec = None
    if args.records:
        import pass_records
        rec = pass_records.Records(root, args.remote, args.records_branch, args.base, args.branch, args.ready, args.all)
    result = run_shard(table, args.shard, root, args.sha, args.timeout_min, rec)
    if rec is not None and result.get("inputs_key") and not result.get("skipped"):
        ok, msg = rec.save(result)
        print("cloud_shard: pass record %s" % ("written" if ok else "not written (%s)" % msg))
    out = args.out or os.path.join(root, ".delivery", "ci-results", result["sha"], args.shard + ".json")
    write_result(result, out)
    print("cloud_shard: %s %s: %s" % (args.shard, result["state"], result["summary"]))
    if args.push:
        ok, msg = push_result(result, root, args.prefix, args.remote)
        print("cloud_shard: %s %s" % ("pushed" if ok else "push failed:", msg), file=sys.stderr if not ok else sys.stdout)
        if not ok:
            return 2
    return {"success": 0, "failure": 1}.get(result["state"], 2)


if __name__ == "__main__":
    sys.exit(main())
