"""DL113: cancel_joined_runs.py cancels active runs of branches already joined, and nothing else."""
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
          / "cancel_joined_runs.py")


def git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


def commit(work, name):
    (work / name).write_text(name)
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", name)
    return git(work, "rev-parse", "HEAD")


FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
d = os.environ["FAKE_GH_DIR"]
if a[:1] == ["--version"]:
    print("gh version 0")
elif a[:2] == ["run", "list"]:
    print(open(d + "/runs.json").read())
elif a[:2] == ["run", "cancel"]:
    open(d + "/cancelled.txt", "a").write(a[2] + "\\n")
    if a[2] in os.environ.get("FAKE_GH_FAIL", "").split(","):
        sys.stderr.write("boom")
        sys.exit(1)
"""


class CancelJoinedTests(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp(prefix="dl113-")).resolve()
        git(base, "init", "-q", "--bare", "-b", "main", "origin.git")
        git(base, "clone", "-q", str(base / "origin.git"), "app1")
        w = self.work = base / "app1"
        git(w, "checkout", "-q", "-b", "main")
        self.main_sha = commit(w, "base")
        git(w, "push", "-q", "origin", "main")
        self.sha = {}
        for b in ("a1", "a2", "a3", "a4"):
            git(w, "checkout", "-q", "-b", b, "main")
            self.sha[b] = commit(w, b)
            git(w, "push", "-q", "origin", b)
        git(w, "checkout", "-q", "-b", "X-integration", "main")
        for b in ("a1", "a2", "a4"):
            git(w, "merge", "-q", "--no-ff", "-m", "join " + b, b)
        git(w, "push", "-q", "origin", "X-integration")
        self.integration_sha = git(w, "rev-parse", "HEAD")
        git(w, "checkout", "-q", "a4")  # a4 is pushed again after the join
        self.sha["a4-new"] = commit(w, "a4-again")
        git(w, "push", "-q", "origin", "a4")
        git(w, "fetch", "-q", "origin")
        self.ghdir = base / "gh"
        self.ghdir.mkdir()
        fake = self.ghdir / "gh"
        fake.write_text(FAKE_GH)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

    def runs(self, rows):
        (self.ghdir / "runs.json").write_text(json.dumps([
            {"databaseId": i, "headBranch": b, "headSha": s, "status": st, "workflowName": "ci", "url": "u"}
            for i, b, s, st in rows]))

    def go(self, *args, fail=""):
        env = dict(os.environ, PATH=str(self.ghdir) + os.pathsep + os.environ["PATH"],
                   FAKE_GH_DIR=str(self.ghdir), FAKE_GH_FAIL=fail)
        return subprocess.run(["python3", str(SCRIPT), "--into", "X-integration", *args],
                              cwd=self.work, env=env, capture_output=True, text=True)

    def cancelled(self):
        f = self.ghdir / "cancelled.txt"
        return f.read_text().split() if f.exists() else []

    def rows(self):
        return [
            (1, "a1", self.sha["a1"], "in_progress"),
            (2, "a2", self.sha["a2"], "queued"),
            (3, "a3", self.sha["a3"], "queued"),          # not merged
            (4, "a4", self.sha["a4-new"], "queued"),      # pushed again after the join
            (5, "X-integration", self.integration_sha, "in_progress"),
            (6, "main", self.main_sha, "in_progress"),
            (7, "a1", self.sha["a1"], "completed"),       # not active
        ]

    def test_yes_cancels_only_merged_unchanged_branches(self):
        self.runs(self.rows())
        p = self.go("--yes")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(sorted(self.cancelled()), ["1", "2"])
        self.assertIn("cancelled 1", p.stdout)

    def test_dry_run_cancels_nothing(self):
        self.runs(self.rows())
        p = self.go()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.cancelled(), [])
        self.assertIn("cancel 1 a1", p.stdout)
        self.assertIn("cancel 2 a2", p.stdout)
        self.assertNotIn("cancel 5", p.stdout)
        self.assertNotIn("cancel 6", p.stdout)

    def test_failing_cancel_exits_1(self):
        self.runs(self.rows())
        p = self.go("--yes", fail="1")
        self.assertEqual(p.returncode, 1)
        self.assertIn("failed 1: boom", p.stdout)
        self.assertIn("2", self.cancelled())

    def test_unknown_integration_branch_exits_2(self):
        self.runs([])
        env = dict(os.environ, PATH=str(self.ghdir) + os.pathsep + os.environ["PATH"], FAKE_GH_DIR=str(self.ghdir))
        p = subprocess.run(["python3", str(SCRIPT), "--into", "nope"], cwd=self.work, env=env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    def test_missing_gh_exits_2(self):
        self.runs([])
        env = dict(os.environ, PATH="/nonexistent-gh:/usr/bin:/bin")
        p = subprocess.run(["python3", str(SCRIPT), "--into", "X-integration"], cwd=self.work, env=env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
