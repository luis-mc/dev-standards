"""DL111: a conflict in one branch does not discard the clean merges of the others."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

JOIN = (Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery" / "join.py")
EXIT_CONFLICT = 3


def git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def commit_file(work, name, text, msg):
    (work / name).write_text(text)
    git(work, "add", name)
    git(work, "commit", "-q", "-m", msg)


def make_repo(conflict=True):
    base = Path(tempfile.mkdtemp(prefix="dl111-")).resolve()
    git(base, "init", "-q", "--bare", "-b", "main", "origin.git")
    git(base, "clone", "-q", str(base / "origin.git"), "app1")
    work = base / "app1"
    commit_file(work, "shared.txt", "base\n", "first")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(work, "branch", "-q", "--set-upstream-to=origin/main")
    git(work, "push", "-q", "origin", "main:integ")
    # integ moves on, so C's change to shared.txt conflicts
    git(work, "checkout", "-q", "-b", "integ-edit", "origin/integ")
    commit_file(work, "shared.txt", "integ\n", "integ edit")
    git(work, "push", "-q", "origin", "integ-edit:integ")
    for name, fname, text in (("A", "a.txt", "a\n"), ("B", "b.txt", "b\n"),
                              ("C", "shared.txt" if conflict else "c.txt", "c\n")):
        git(work, "checkout", "-q", "-b", name, "origin/main")
        commit_file(work, fname, text, "work " + name)
        git(work, "push", "-q", "origin", name)
    git(work, "checkout", "-q", "main")
    git(work, "branch", "-q", "-D", "integ-edit", "A", "B", "C")
    return work


def run_join(work, *args):
    return subprocess.run(["python3", str(JOIN), "--into", "integ", *args], cwd=work,
                          capture_output=True, text=True)


def files_on(work, ref):
    return set(git(work, "ls-tree", "-r", "--name-only", ref).split())


class JoinKeepsCleanTests(unittest.TestCase):
    def test_conflict_last_keeps_a_and_b_and_pushes(self):
        work = make_repo()
        p = run_join(work, "--push", "A", "B", "C")
        self.assertEqual(p.returncode, EXIT_CONFLICT, p.stderr)
        git(work, "fetch", "-q", "origin")
        remote = files_on(work, "origin/integ")
        self.assertTrue({"a.txt", "b.txt"} <= remote)
        self.assertNotIn("<<<<<<<", git(work, "show", "origin/integ:shared.txt"))
        self.assertIn("C conflicts with integ", p.stderr)
        self.assertIn("shared.txt", p.stderr)
        self.assertIn("kept the clean merges (A, B)", p.stderr)
        res = json.loads((work / ".delivery" / "join-result.json").read_text())
        self.assertEqual(res["joined"], ["A", "B"])
        self.assertEqual(res["conflicting"], {"C": ["shared.txt"]})
        self.assertTrue(res["pushed"])

    def test_conflict_in_the_middle_keeps_both_sides(self):
        work = make_repo()
        p = run_join(work, "--push", "A", "C", "B")
        self.assertEqual(p.returncode, EXIT_CONFLICT, p.stderr)
        git(work, "fetch", "-q", "origin")
        self.assertTrue({"a.txt", "b.txt"} <= files_on(work, "origin/integ"))
        res = json.loads((work / ".delivery" / "join-result.json").read_text())
        self.assertEqual(res["joined"], ["A", "B"])
        self.assertEqual(list(res["conflicting"]), ["C"])

    def test_without_push_clean_merges_stay_on_local_branch(self):
        work = make_repo()
        p = run_join(work, "A", "B", "C")
        self.assertEqual(p.returncode, EXIT_CONFLICT, p.stderr)
        self.assertTrue({"a.txt", "b.txt"} <= files_on(work, "integ"))
        self.assertNotIn("a.txt", files_on(work, "origin/integ"))
        self.assertIn("not pushed", p.stderr)
        self.assertEqual(git(work, "status", "--porcelain", "--untracked-files=no").strip(), "")

    def test_all_clean_is_unchanged(self):
        work = make_repo(conflict=False)
        p = run_join(work, "--push", "A", "B", "C")
        self.assertEqual(p.returncode, 0, p.stderr)
        git(work, "fetch", "-q", "origin")
        self.assertTrue({"a.txt", "b.txt", "c.txt"} <= files_on(work, "origin/integ"))
        res = json.loads((work / ".delivery" / "join-result.json").read_text())
        self.assertEqual(res["joined"], ["A", "B", "C"])
        self.assertNotIn("partial", res)


if __name__ == "__main__":
    unittest.main()
