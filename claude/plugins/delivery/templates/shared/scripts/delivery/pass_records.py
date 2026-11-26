#!/usr/bin/env python3
"""Inputs key and pass records: skip a CI shard whose inputs already passed (DL20, learnings L4 and L5).

    pass_records.py key     --shard ID [--table T]
    pass_records.py check   --shard ID --read-from BRANCH [--read-from ...] [--table T] [--remote origin]
    pass_records.py write   --shard ID --state success|failure --write-as BRANCH [--table T] [--remote origin]
    pass_records.py cleanup [--keep 20] [--default main] [--dry-run] [--remote origin]
    pass_records.py to-result   --shard ID --out FILE [--lane L --arch A --package P] [--default main] [--table T]
    pass_records.py copy-to-main --from-branch B [--default main] [--remote origin]

Inputs key. A shard lists what it depends on in the shard table: `inputs` (paths of files or folders, for
example its workspaces and their dependencies) and, for the whole table, `root_files` (files that change every
key, such as the lock file). The key is a SHA-256 of the shard id, its OS, its expanded commands and the git
blob id of every file under those paths at HEAD. Change one byte of one such file and the key changes.
A shard with `"tree": true` instead keys on the git tree hash of HEAD alone (DP9): the same tree, the same
key, on any branch. Use it for setup and the secret scan. A shard with no `inputs`, a path that matches nothing, or uncommitted changes under its paths has NO key: it
always runs. A missing key never skips.

Pass records. Records live on one orphan branch (default `ci-pass-records`), one file per
`<branch>/<shard>/<key>.json`. A file is never edited by two shards, so shards do not race; a push that loses a
race is fetched and tried again. A record holds the key, the shard, the state, the sha, the branch and the time.

Reading. Only `state: success` with the same key skips a shard. A failed record never skips. A ready pull
request to the base branch reads only the base branch's records, never its own branch's (`read_sources`).
A run on any other branch reads its own records and the base branch's. `--all` ignores every record.

Cleanup. `cleanup` removes the records of branches that no longer exist on the remote and keeps the newest
`--keep` records of each shard. It never deletes the records branch and never touches a branch that still exists.

Lane results (DL-118). `to-result` turns a pass record of the default branch into a lane result file for
`lifecycle_release_check.py`: status `pass`, `source: "record"`, the key and the record's branch. It reads only
the default branch's records and only a record whose own `branch` is the default branch, never the pull
request's. A miss (no key, no record, another branch) exits 1 and writes nothing, so the lane runs. A lane with no
`inputs` list never has a key and always runs. `copy-to-main` copies the success records of one branch to the
default branch (a push to main skipped because its tree equals a passed pull-request tree has no run of its own,
so main would hold no record); the copies say `copied_from`.

Exit: check 0 = hit (skip), 1 = miss (run); key 0 = key printed, 3 = no key; others 0 ok, 2 error.
Standard library only; plain git, no GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import quote

RECORDS_BRANCH = "ci-pass-records"
SCHEMA = 1
PUSH_TRIES = 5


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git(root, *args, env=None, input_=None):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False,
                          env=env, input=input_)


def slug(name: str) -> str:
    """A branch or shard name as one safe path part."""
    return quote(name, safe="") or "_"


def record_path(branch: str, shard: str, key: str) -> str:
    return "%s/%s/%s.json" % (slug(branch), slug(shard), key)


def read_sources(branch: str, base: str, ready_pr_to_base: bool = False) -> list[str]:
    """Whose records a run may read (L5). A ready PR to the base reads only the base's."""
    if ready_pr_to_base or branch == base:
        return [base]
    return [branch, base]


# --------------------------------------------------------------------------
# the inputs key
# --------------------------------------------------------------------------

def expand_commands(shard: dict, tests: dict) -> list[str]:
    out = []
    for raw in shard.get("commands") or []:
        m = re.fullmatch(r"@([A-Za-z0-9_.-]+)", str(raw).strip())
        out.append(tests[m.group(1)] if m and isinstance(tests.get(m.group(1)), str) else str(raw))
    return out


def tree_entries(root, paths: list[str]):
    """[(blob id, path)] under `paths` at HEAD, or (None, reason)."""
    entries = []
    for p in paths:
        r = git(root, "ls-tree", "-r", "HEAD", "--", p)
        if r.returncode:
            return None, "git ls-tree failed for %s" % p
        rows = []
        for ln in r.stdout.splitlines():
            meta, _, name = ln.partition("\t")
            if name:
                rows.append((meta.split()[2], name))
        if not rows:
            return None, "input path %r matches no committed file" % p
        entries += rows
    return sorted(set(entries), key=lambda e: e[1]), None


def tree_key(root, shard_id: str, os_name=None):
    """(key, reason) from the git tree hash of HEAD (DP9, D9): the same tree gives the same key on any branch,
    so a pass for a shard that does not depend on the branch name (setup, secret scan) is reused. No key when
    the working tree has uncommitted changes."""
    if git(root, "status", "--porcelain", "--untracked-files=all").stdout.strip():
        return None, "uncommitted changes in the working tree"
    r = git(root, "rev-parse", "HEAD^{tree}")
    if r.returncode or not r.stdout.strip():
        return None, "git rev-parse HEAD^{tree} failed"
    blob = {"v": SCHEMA, "shard": shard_id, "os": os_name, "tree": r.stdout.strip()}
    return hashlib.sha256(json.dumps(blob, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), None


def inputs_key(root, table: dict, shard_id: str):
    """(key, reason). key is a 64-character hex string, or None with the reason there is no key."""
    shard = next((s for s in table.get("shards", []) if isinstance(s, dict) and s.get("id") == shard_id), None)
    if shard is None:
        return None, "no shard %r in the table" % shard_id
    if shard.get("tree") is True:
        return tree_key(root, shard_id, shard.get("os"))
    inputs = shard.get("inputs")
    if not isinstance(inputs, list) or not inputs or not all(isinstance(p, str) and p for p in inputs):
        return None, "shard %r lists no `inputs`, so it always runs" % shard_id
    roots = table.get("root_files") if isinstance(table.get("root_files"), list) else []
    paths = [p for p in list(inputs) + [str(r) for r in roots]]
    if git(root, "status", "--porcelain", "--untracked-files=all", "--", *paths).stdout.strip():
        return None, "uncommitted changes under the shard's inputs"
    entries, why = tree_entries(root, paths)
    if entries is None:
        return None, why
    tests = table.get("tests") if isinstance(table.get("tests"), dict) else {}
    blob = {"v": SCHEMA, "shard": shard_id, "os": shard.get("os"), "commands": expand_commands(shard, tests),
            "files": entries}
    return hashlib.sha256(json.dumps(blob, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), None


# --------------------------------------------------------------------------
# the records branch
# --------------------------------------------------------------------------

def local_ref(remote: str, branch: str) -> str:
    return "refs/pass-records/%s/%s" % (remote, branch)


def fetch(root, remote: str, branch: str) -> bool:
    """Fetch the records branch into a private ref. False when the remote has no such branch (or no network)."""
    r = git(root, "fetch", "--quiet", "--no-tags", remote, "+refs/heads/%s:%s" % (branch, local_ref(remote, branch)))
    return r.returncode == 0


def read_file(root, remote: str, branch: str, path: str):
    r = git(root, "show", "%s:%s" % (local_ref(remote, branch), path))
    if r.returncode:
        return None
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def lookup(root, remote: str, branch: str, sources: list[str], shard: str, key: str):
    """The success record that skips this shard, or None. One fetch, then local reads."""
    if not fetch(root, remote, branch):
        return None
    for src in sources:
        rec = read_file(root, remote, branch, record_path(src, shard, key))
        if rec and rec.get("state") == "success" and rec.get("key") == key and rec.get("shard") == shard:
            return rec
    return None


def commit_change(root, remote: str, branch: str, add: dict, remove: list[str], message: str):
    """Add and remove files on the records branch with plumbing and push; retry when a race is lost.
    Returns (ok, message)."""
    last = ""
    for attempt in range(PUSH_TRIES):
        have = fetch(root, remote, branch)
        parent = git(root, "rev-parse", local_ref(remote, branch)).stdout.strip() if have else ""
        tmp = tempfile.mkdtemp(prefix="pass-records-")
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index"), GIT_AUTHOR_NAME="ci-records",
                   GIT_AUTHOR_EMAIL="ci-records@localhost", GIT_COMMITTER_NAME="ci-records",
                   GIT_COMMITTER_EMAIL="ci-records@localhost")
        try:
            if parent:
                git(root, "read-tree", parent, env=env)
            for path in remove:
                git(root, "update-index", "--force-remove", path, env=env)
            for path, text in add.items():
                p = os.path.join(tmp, "blob")
                with open(p, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
                oid = git(root, "hash-object", "-w", p, env=env).stdout.strip()
                git(root, "update-index", "--add", "--cacheinfo", "100644,%s,%s" % (oid, path), env=env)
            tree = git(root, "write-tree", env=env).stdout.strip()
            args = ["commit-tree", tree, "-m", message] + (["-p", parent] if parent else [])
            commit = git(root, *args, env=env)
            if commit.returncode:
                return False, commit.stderr.strip()
            pushed = git(root, "push", "--quiet", remote, "%s:refs/heads/%s" % (commit.stdout.strip(), branch))
            if pushed.returncode == 0:
                git(root, "update-ref", local_ref(remote, branch), commit.stdout.strip())
                return True, commit.stdout.strip()
            last = pushed.stderr.strip()
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
        time.sleep(0.2 * (attempt + 1))
    return False, "push lost the race %d times: %s" % (PUSH_TRIES, last)


def to_result(root, remote: str, branch: str, table: dict, shard_id: str, default: str, out: str,
              lane=None, arch=None, package=None):
    """(code, message). 0 and a lane result file written from a default-branch pass record; 1 on any miss."""
    key, why = inputs_key(root, table, shard_id)
    if key is None:
        return 1, "no key (%s)" % why
    rec = lookup(root, remote, branch, [default], shard_id, key)
    if not rec or rec.get("branch") != default:
        return 1, "miss: no pass record of %s with key %s" % (default, key[:12])
    result = {"lane": lane or shard_id, "arch": arch, "package": package, "status": "pass", "failed": [],
              "checks": 0, "source": "record", "shard": shard_id, "key": key, "record_branch": rec["branch"],
              "record_sha": rec.get("sha", "")}
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(result, indent=2) + "\n")
    return 0, "record %s on %s" % (key[:12], default)


def copy_to_main(root, remote: str, branch: str, from_branch: str, default: str):
    """(count, error). Copy the success records of `from_branch` to `default`; one already there stays."""
    if from_branch == default or not fetch(root, remote, branch):
        return 0, None
    prefix = slug(from_branch) + "/"
    records = list_records(root, remote, branch)
    have = {p for p, _ in records if p.startswith(slug(default) + "/")}
    add = {}
    for path, _ in records:
        if not path.startswith(prefix):
            continue
        rec = read_file(root, remote, branch, path)
        if not rec or rec.get("state") != "success" or not rec.get("key") or not rec.get("shard"):
            continue
        dest = record_path(default, rec["shard"], rec["key"])
        if dest in have or dest in add:
            continue
        add[dest] = json.dumps(dict(rec, branch=default, copied_from=from_branch, at=now_iso()), indent=2) + "\n"
    if not add:
        return 0, None
    ok, msg = commit_change(root, remote, branch, add, [],
                            "copy %d pass records of %s to %s" % (len(add), from_branch, default))
    return (len(add), None) if ok else (0, msg)


def make_record(shard: str, key: str, state: str, sha: str, branch: str, seconds: float = 0.0) -> dict:
    return {"schema": SCHEMA, "shard": shard, "key": key, "state": state, "sha": sha, "branch": branch,
            "seconds": round(seconds, 1), "at": now_iso()}


def write(root, remote: str, branch: str, write_as: str, rec: dict):
    path = record_path(write_as, rec["shard"], rec["key"])
    return commit_change(root, remote, branch, {path: json.dumps(rec, indent=2) + "\n"}, [],
                         "pass record %s %s %s" % (rec["shard"], rec["key"][:12], rec["state"]))


# --------------------------------------------------------------------------
# cleanup
# --------------------------------------------------------------------------

def remote_heads(root, remote: str):
    r = git(root, "ls-remote", "--heads", remote)
    if r.returncode:
        return None
    return {ln.split("refs/heads/", 1)[1] for ln in r.stdout.splitlines() if "refs/heads/" in ln}


def list_records(root, remote: str, branch: str):
    """[(path, at)] for every record file on the branch."""
    r = git(root, "ls-tree", "-r", "--name-only", local_ref(remote, branch))
    if r.returncode:
        return []
    out = []
    for path in r.stdout.splitlines():
        m = re.fullmatch(r"([^/]+)/([^/]+)/[0-9a-f]{64}\.json", path)
        if not m:
            continue
        rec = read_file(root, remote, branch, path) or {}
        out.append((path, str(rec.get("at", ""))))
    return out


def plan_cleanup(records: list, live_slugs: set, default_slug: str, keep: int) -> list[str]:
    """Paths to remove: a branch that is gone, and all but the newest `keep` of one (branch, shard)."""
    drop, groups = [], {}
    for path, at in records:
        b, s = path.split("/")[:2]
        if b != default_slug and b not in live_slugs:
            drop.append(path)
        else:
            groups.setdefault((b, s), []).append((at, path))
    for items in groups.values():
        items.sort(reverse=True)
        drop += [p for _, p in items[keep:]]
    return sorted(drop)


def cleanup(root, remote: str, branch: str, default: str, keep: int, dry: bool = False):
    """Returns (removed paths, error). Never touches records of a live branch beyond the keep limit."""
    if not fetch(root, remote, branch):
        return [], None  # no records branch yet: nothing to do
    heads = remote_heads(root, remote)
    if heads is None:
        return [], "cannot list the branches on %s; nothing removed" % remote
    drop = plan_cleanup(list_records(root, remote, branch), {slug(h) for h in heads}, slug(default), keep)
    if drop and not dry:
        ok, msg = commit_change(root, remote, branch, {}, drop, "clean %d pass records" % len(drop))
        if not ok:
            return [], msg
    return drop, None


def drop_branch(root, remote: str, branch: str, gone: str):
    """Remove every record of one deleted branch. Best effort. Returns (count, error)."""
    if not fetch(root, remote, branch):
        return 0, None
    prefix = slug(gone) + "/"
    paths = [p for p, _ in list_records(root, remote, branch) if p.startswith(prefix)]
    if not paths:
        return 0, None
    ok, msg = commit_change(root, remote, branch, {}, paths, "drop records of %s" % gone)
    return (len(paths), None) if ok else (0, msg)


# --------------------------------------------------------------------------
# the part cloud_shard.py uses
# --------------------------------------------------------------------------

class Records:
    """Settings of one run. `consult` before running a shard, `save` after."""

    def __init__(self, root, remote="origin", branch=RECORDS_BRANCH, base="main", current="", ready=False,
                 ignore=False):
        self.root, self.remote, self.branch, self.base = root, remote, branch, base
        self.current = current or git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or base
        self.ready, self.ignore = ready, ignore

    def consult(self, table: dict, shard_id: str):
        """(key, hit record or None, note). With --all the key is still computed but nothing is read."""
        key, why = inputs_key(self.root, table, shard_id)
        if key is None:
            return None, None, why
        if self.ignore:
            return key, None, "records ignored (--all)"
        sources = read_sources(self.current, self.base, self.ready)
        return key, lookup(self.root, self.remote, self.branch, sources, shard_id, key), ""

    def save(self, result: dict):
        """Write a success or failure record. An error is never recorded."""
        key = result.get("inputs_key")
        if not key or result.get("skipped") or result.get("state") not in ("success", "failure"):
            return False, "nothing to record"
        secs = sum(c.get("seconds", 0) for c in result.get("commands", []))
        rec = make_record(result["shard"], key, result["state"], result["sha"], self.current, secs)
        return write(self.root, self.remote, self.branch, self.current, rec)


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------

def load_table(root, path):
    with open(os.path.join(root, path.replace("/", os.sep)), encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("shards"), list):
        raise ValueError("the shard table needs a `shards` list")
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pass_records.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["key", "check", "write", "cleanup", "to-result", "copy-to-main"])
    ap.add_argument("--shard")
    ap.add_argument("--table", default="scripts/delivery/ci-shards.json")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--records-branch", default=RECORDS_BRANCH)
    ap.add_argument("--read-from", action="append", default=[], metavar="BRANCH")
    ap.add_argument("--write-as", metavar="BRANCH")
    ap.add_argument("--state", choices=["success", "failure"])
    ap.add_argument("--keep", type=int, default=20, help="cleanup: records kept for each branch and shard")
    ap.add_argument("--default", default="main", help="cleanup: the base branch; its records are never dropped")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", help="to-result: the lane result file to write")
    ap.add_argument("--lane")
    ap.add_argument("--arch")
    ap.add_argument("--package")
    ap.add_argument("--from-branch", help="copy-to-main: the branch whose success records are copied")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    if a.action == "cleanup":
        removed, err = cleanup(root, a.remote, a.records_branch, a.default, a.keep, a.dry_run)
        for p in removed:
            print(("would remove " if a.dry_run else "removed ") + p)
        if err:
            print("pass_records: " + err, file=sys.stderr)
            return 2
        print("pass_records: %d record(s) %s" % (len(removed), "would go" if a.dry_run else "removed"))
        return 0
    if a.action == "copy-to-main":
        if not a.from_branch:
            print("pass_records: copy-to-main needs --from-branch", file=sys.stderr)
            return 2
        n, err = copy_to_main(root, a.remote, a.records_branch, a.from_branch, a.default)
        if err:
            print("pass_records: " + err, file=sys.stderr)
            return 2
        print("pass_records: %d record(s) copied to %s" % (n, a.default))
        return 0
    if not a.shard:
        print("pass_records: --shard is required", file=sys.stderr)
        return 2
    try:
        table = load_table(root, a.table)
    except (OSError, ValueError) as exc:
        print("pass_records: cannot read the shard table (%s)" % exc, file=sys.stderr)
        return 2
    if a.action == "to-result":
        if not a.out:
            print("pass_records: to-result needs --out", file=sys.stderr)
            return 2
        code, msg = to_result(root, a.remote, a.records_branch, table, a.shard, a.default, a.out,
                              a.lane, a.arch, a.package)
        print("pass_records: " + msg)
        return code
    key, why = inputs_key(root, table, a.shard)
    if a.action == "key":
        print(key if key else "none: " + why)
        return 0 if key else 3
    if key is None:
        print("pass_records: no key (%s)" % why)
        return 1 if a.action == "check" else 3
    if a.action == "check":
        rec = lookup(root, a.remote, a.records_branch, a.read_from, a.shard, key)
        print(json.dumps(rec) if rec else "miss")
        return 0 if rec else 1
    if not a.write_as or not a.state:
        print("pass_records: write needs --write-as and --state", file=sys.stderr)
        return 2
    sha = git(root, "rev-parse", "HEAD").stdout.strip()
    ok, msg = write(root, a.remote, a.records_branch, a.write_as, make_record(a.shard, key, a.state, sha, a.write_as))
    print("pass_records: %s %s" % ("written" if ok else "write failed:", msg), file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
