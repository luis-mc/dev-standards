#!/usr/bin/env python3
"""DL20: inputs key and pass records (pass_records.py, and its use in cloud_shard.py and cleanup).
No network: a local bare git repository is the fake remote. Standard library only."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "claude/plugins/delivery/templates/shared/scripts/delivery"
sys.path.insert(0, str(SCRIPTS))

import cloud_shard as S  # noqa: E402
import pass_records as P  # noqa: E402

PY = sys.executable.replace("\\", "/")
THIS = S.this_os()
ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **ENV})
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def counter_cmd(name):
    """A command that appends a line to a file: counts how often the shard really ran."""
    return '"%s" -c "open(\'%s\', \'a\').write(\'x\')"' % (PY, name)


def make_project(commands=None):
    base = Path(tempfile.mkdtemp(prefix="records-"))
    remote, work = base / "remote.git", base / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    git(work, "checkout", "-q", "-b", "main")
    (work / "scripts/delivery").mkdir(parents=True)
    (work / "app").mkdir()
    (work / "app/a.txt").write_text("a1")
    (work / "other").mkdir()
    (work / "other/b.txt").write_text("b1")
    (work / "lock.txt").write_text("l1")
    (work / ".gitignore").write_text("ran*.txt\n.delivery/\n")
    table = {"root_files": ["lock.txt"], "tests": {"count": counter_cmd("ran.txt")}, "shards": [
        {"id": "unit", "os": THIS, "inputs": ["app"], "commands": commands or ["@count"]},
        {"id": "noinputs", "os": THIS, "commands": ["@count"]},
        {"id": "fails", "os": THIS, "inputs": ["app"],
         "commands": [counter_cmd("ran-fail.txt"), '"%s" -c "import sys; sys.exit(3)"' % PY]}]}
    (work / "scripts/delivery/ci-shards.json").write_text(json.dumps(table))
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "c1")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "main")
    return work, remote


def commit_file(work, rel, text):
    (work / rel).write_text(text)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "change " + rel)


def runs(work, name="ran.txt"):
    p = work / name
    return len(p.read_text()) if p.exists() else 0


def shard(work, shard_id="unit", *extra):
    """cloud_shard main with --records; returns (exit code, result dict)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = S.main(["run", "--shard", shard_id, "--root", str(work), "--records", *extra])
    newest = max((work / ".delivery/ci-results").glob("*/%s.json" % shard_id), key=lambda p: p.stat().st_mtime_ns)
    return code, json.loads(newest.read_text())


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.work, _ = make_project()
        self.table = P.load_table(str(self.work), "scripts/delivery/ci-shards.json")

    def key(self, sid="unit", table=None):
        return P.inputs_key(str(self.work), table or self.table, sid)

    def test_same_inputs_same_key(self):
        k1, _ = self.key()
        self.assertEqual(len(k1), 64)
        commit_file(self.work, "other/b.txt", "b2")  # outside the shard's inputs
        self.assertEqual(self.key()[0], k1)

    def test_changed_input_file_changes_key(self):
        k1, _ = self.key()
        commit_file(self.work, "app/a.txt", "a2")
        self.assertNotEqual(self.key()[0], k1)

    def test_new_file_in_input_folder_changes_key(self):
        k1, _ = self.key()
        commit_file(self.work, "app/new.txt", "n")
        self.assertNotEqual(self.key()[0], k1)

    def test_root_file_changes_key(self):
        k1, _ = self.key()
        commit_file(self.work, "lock.txt", "l2")
        self.assertNotEqual(self.key()[0], k1)

    def test_changed_command_changes_key(self):
        k1, _ = self.key()
        self.table["tests"]["count"] = counter_cmd("other.txt")
        self.assertNotEqual(self.key()[0], k1)

    def test_shard_id_is_in_the_key(self):
        self.assertNotEqual(self.key("unit")[0], self.key("fails")[0])

    def test_no_key_cases_never_skip(self):
        self.assertIsNone(self.key("noinputs")[0])
        t = json.loads(json.dumps(self.table))
        t["shards"][0]["inputs"] = ["missing-folder"]
        self.assertIsNone(self.key(table=t)[0])
        (self.work / "app/a.txt").write_text("dirty")
        key, why = self.key()
        self.assertIsNone(key)
        self.assertIn("uncommitted", why)


class SkipTests(unittest.TestCase):
    def setUp(self):
        self.work, self.remote = make_project()

    def test_second_run_is_skipped_in_seconds(self):
        code, res = shard(self.work)
        self.assertEqual((code, res["state"], runs(self.work)), (0, "success", 1))
        self.assertNotIn("skipped", res)
        t0 = time.monotonic()
        code, res = shard(self.work)
        took = time.monotonic() - t0
        self.assertEqual((code, res["state"], res["skipped"], runs(self.work)), (0, "success", True, 1))
        self.assertEqual(res["commands"], [])
        self.assertEqual(res["record"]["key"], res["inputs_key"])
        self.assertLess(took, 5)

    def test_changed_file_runs_again(self):
        shard(self.work)
        commit_file(self.work, "app/a.txt", "a2")
        code, res = shard(self.work)
        self.assertEqual((res.get("skipped"), runs(self.work)), (None, 2))
        self.assertEqual(shard(self.work)[1]["skipped"], True)

    def test_failed_record_never_skips(self):
        for n in (1, 2):
            code, res = shard(self.work, "fails")
            self.assertEqual((code, res["state"], runs(self.work, "ran-fail.txt")), (1, "failure", n))
        rec = P.read_file(str(self.work), "origin", P.RECORDS_BRANCH, P.record_path("main", "fails", res["inputs_key"]))
        self.assertEqual(rec["state"], "failure")

    def test_a_later_pass_replaces_the_failed_record(self):
        key, _ = P.inputs_key(str(self.work), P.load_table(str(self.work), "scripts/delivery/ci-shards.json"), "unit")
        sha = git(self.work, "rev-parse", "HEAD")
        P.write(str(self.work), "origin", P.RECORDS_BRANCH, "main", P.make_record("unit", key, "failure", sha, "main"))
        self.assertEqual(shard(self.work)[1].get("skipped"), None)
        self.assertEqual(shard(self.work)[1]["skipped"], True)

    def test_all_ignores_records(self):
        shard(self.work)
        code, res = shard(self.work, "unit", "--all")
        self.assertEqual((res.get("skipped"), runs(self.work)), (None, 2))

    def test_no_inputs_always_runs_and_writes_nothing(self):
        shard(self.work, "noinputs")
        shard(self.work, "noinputs")
        self.assertEqual(runs(self.work), 2)
        self.assertFalse(P.fetch(str(self.work), "origin", P.RECORDS_BRANCH))

    def test_error_is_never_recorded(self):
        code, res = shard(self.work, "unit", "--sha", "0" * 40)
        self.assertEqual((code, res["state"]), (2, "error"))
        self.assertFalse(P.fetch(str(self.work), "origin", P.RECORDS_BRANCH))

    def test_unreachable_remote_runs_the_shard(self):
        git(self.work, "remote", "set-url", "origin", str(self.work / "nowhere.git"))
        code, res = shard(self.work)
        self.assertEqual((code, res.get("skipped"), runs(self.work)), (0, None, 1))


class ReadRuleTests(unittest.TestCase):
    """L5: a ready PR to the base reads only the base's records."""

    def setUp(self):
        self.work, self.remote = make_project()
        git(self.work, "checkout", "-q", "-b", "feat/x")

    def test_sources(self):
        self.assertEqual(P.read_sources("feat/x", "main", True), ["main"])
        self.assertEqual(P.read_sources("feat/x", "main"), ["feat/x", "main"])
        self.assertEqual(P.read_sources("main", "main"), ["main"])

    def test_own_branch_record_skips_a_draft_but_not_a_ready_pr(self):
        shard(self.work)  # writes records/feat%2Fx/...
        self.assertEqual(shard(self.work)[1]["skipped"], True)
        code, res = shard(self.work, "unit", "--ready")
        self.assertEqual((res.get("skipped"), runs(self.work)), (None, 2))

    def test_base_record_skips_a_ready_pr(self):
        git(self.work, "checkout", "-q", "main")
        shard(self.work)  # the base writes its own record
        git(self.work, "checkout", "-q", "feat/x")
        code, res = shard(self.work, "unit", "--ready")
        self.assertEqual((res["skipped"], runs(self.work)), (True, 1))
        self.assertEqual(res["record"]["branch"], "main")


class RaceAndCleanupTests(unittest.TestCase):
    def setUp(self):
        self.work, self.remote = make_project()
        self.other = Path(tempfile.mkdtemp(prefix="records-b-")) / "work"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.other)], check=True)
        self.w = str(self.work)

    def rec(self, branch, shard_id, n, state="success"):
        key = "%064x" % n
        r = P.make_record(shard_id, key, state, "a" * 40, branch)
        r["at"] = "2026-11-%02dT00:00:00Z" % (n % 28 + 1)
        return r

    def test_two_writers_both_land(self):
        a, b = self.rec("b1", "unit", 1), self.rec("b2", "unit", 2)
        # both start from the same remote state: the second push is refused once and is retried
        self.assertTrue(P.write(self.w, "origin", P.RECORDS_BRANCH, "b1", a)[0])
        P.fetch(str(self.other), "origin", P.RECORDS_BRANCH)
        self.assertTrue(P.write(self.w, "origin", P.RECORDS_BRANCH, "b1", self.rec("b1", "unit", 3))[0])
        self.assertTrue(P.write(str(self.other), "origin", P.RECORDS_BRANCH, "b2", b)[0])
        P.fetch(self.w, "origin", P.RECORDS_BRANCH)
        names = {p for p, _ in P.list_records(self.w, "origin", P.RECORDS_BRANCH)}
        self.assertEqual(len(names), 3)

    def test_cleanup_drops_dead_branches_and_keeps_newest(self):
        git(self.work, "push", "-q", "origin", "main:live")
        for branch, n in (("live", 1), ("dead", 2), ("main", 3), ("main", 4), ("main", 5)):
            P.write(self.w, "origin", P.RECORDS_BRANCH, branch, self.rec(branch, "unit", n))
        removed, err = P.cleanup(self.w, "origin", P.RECORDS_BRANCH, "main", keep=2, dry=True)
        self.assertEqual(len(removed), 2)  # dead + the oldest main record
        removed, err = P.cleanup(self.w, "origin", P.RECORDS_BRANCH, "main", keep=2)
        self.assertIsNone(err)
        left = {p.split("/")[0] for p, _ in P.list_records(self.w, "origin", P.RECORDS_BRANCH)}
        self.assertEqual(left, {"live", "main"})
        self.assertEqual(sum(1 for p, _ in P.list_records(self.w, "origin", P.RECORDS_BRANCH) if p.startswith("main/")), 2)
        self.assertTrue(P.fetch(self.w, "origin", P.RECORDS_BRANCH))  # the branch itself stays

    def test_cleanup_removes_nothing_when_the_branch_list_fails(self):
        P.write(self.w, "origin", P.RECORDS_BRANCH, "dead", self.rec("dead", "unit", 1))
        orig = P.remote_heads
        P.remote_heads = lambda *a: None
        try:
            removed, err = P.cleanup(self.w, "origin", P.RECORDS_BRANCH, "main", keep=5)
        finally:
            P.remote_heads = orig
        self.assertEqual((removed, bool(err)), ([], True))
        self.assertEqual(len(P.list_records(self.w, "origin", P.RECORDS_BRANCH)), 1)

    def test_drop_branch_removes_only_that_branch(self):
        P.write(self.w, "origin", P.RECORDS_BRANCH, "gone", self.rec("gone", "unit", 1))
        P.write(self.w, "origin", P.RECORDS_BRANCH, "kept", self.rec("kept", "unit", 2))
        self.assertEqual(P.drop_branch(self.w, "origin", P.RECORDS_BRANCH, "gone"), (1, None))
        self.assertEqual([p.split("/")[0] for p, _ in P.list_records(self.w, "origin", P.RECORDS_BRANCH)], ["kept"])


class CliTests(unittest.TestCase):
    def test_check_and_write_cli(self):
        work, _ = make_project()
        run = lambda *a: subprocess.run([PY, str(SCRIPTS / "pass_records.py"), *a, "--root", str(work)],  # noqa: E731
                                        capture_output=True, text=True, env={**os.environ, **ENV})
        self.assertEqual(run("key", "--shard", "unit").returncode, 0)
        self.assertEqual(run("key", "--shard", "noinputs").returncode, 3)
        self.assertEqual(run("check", "--shard", "unit", "--read-from", "main").returncode, 1)
        self.assertEqual(run("write", "--shard", "unit", "--state", "success", "--write-as", "main").returncode, 0)
        self.assertEqual(run("check", "--shard", "unit", "--read-from", "main").returncode, 0)
        self.assertEqual(run("check", "--shard", "unit", "--read-from", "other").returncode, 1)
        self.assertEqual(run("cleanup", "--dry-run").returncode, 0)


if __name__ == "__main__":
    unittest.main()
