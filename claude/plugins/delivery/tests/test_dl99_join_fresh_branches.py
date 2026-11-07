"""DL99: the cleanup a join starts keeps fresh local branches and branches with a running agent."""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

CLEANUP = (Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery" / "cleanup.py")
JOIN = CLEANUP.with_name("join.py")


def git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def make_repo():
    base = Path(tempfile.mkdtemp(prefix="dl99-")).resolve()
    git(base, "init", "-q", "--bare", "-b", "main", "origin.git")
    work = base / "app1"
    git(base, "clone", "-q", str(base / "origin.git"), "app1")
    (work / "a.txt").write_text("a\n")
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "first")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(work, "branch", "-q", "--set-upstream-to=origin/main")
    for name in ("train-old", "fresh-new", "agent-run"):
        git(work, "branch", name)  # no commit of their own: scaffolding branches
    return work


def run_cleanup(work, since, extra_env=None):
    env = dict(os.environ, PATH="/nonexistent-gh:" + os.environ["PATH"])
    return subprocess.run(["python3", str(CLEANUP), "--local", "--remote", "origin",
                           "--keep-fresh-since", str(since)], cwd=work, capture_output=True, text=True, env=env)


def branches(work):
    return set(git(work, "for-each-ref", "--format=%(refname:short)", "refs/heads/").split())


class FreshBranchTests(unittest.TestCase):
    def test_old_branches_are_removed(self):
        work = make_repo()
        run_cleanup(work, int(time.time()) + 3600)  # the join "started" after every branch was made
        self.assertNotIn("train-old", branches(work))
        self.assertNotIn("fresh-new", branches(work))

    def test_branch_created_after_join_start_is_kept_and_reported(self):
        work = make_repo()
        p = run_cleanup(work, int(time.time()) - 3600)  # every branch is newer than the join start
        self.assertIn("train-old", branches(work))
        self.assertIn("cleanup: skipped fresh-new: created after the join started", p.stderr)
        self.assertIn("fresh-new  kept: created after the join started", p.stdout)

    def test_branch_with_running_agent_is_kept(self):
        work = make_repo()
        (work / ".delivery").mkdir()
        (work / ".delivery" / "ledger.json").write_text(json.dumps({"agents": [
            {"task": "X1", "branch": "agent-run", "state": "running"},
            {"task": "X2", "branch": "train-old", "state": "done"}]}))
        p = run_cleanup(work, int(time.time()) + 3600)
        self.assertIn("agent-run", branches(work))
        self.assertNotIn("train-old", branches(work))
        self.assertIn("cleanup: skipped agent-run: a running agent in the ledger works on it", p.stderr)

    def test_unreadable_ledger_skips_only_the_agent_check(self):
        work = make_repo()
        (work / ".delivery").mkdir()
        (work / ".delivery" / "ledger.json").write_text("{not json")
        run_cleanup(work, int(time.time()) + 3600)
        self.assertNotIn("agent-run", branches(work))
        work2 = make_repo()
        run_cleanup(work2, int(time.time()) - 3600)
        self.assertIn("agent-run", branches(work2))

    def test_join_passes_its_start_time(self):
        text = JOIN.read_text(encoding="utf-8")
        self.assertIn('"--keep-fresh-since", str(started)', text)


if __name__ == "__main__":
    unittest.main()
