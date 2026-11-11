"""DL241 join: sibling branches off one contract branch, skipped lines, partial join summary and exit codes."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

JOIN = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery" / "join.py"
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com", LUISMC_DOCS_WORK="/nonexistent/docs_work.py")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, env=ENV, check=True, capture_output=True, text=True).stdout


def commit(w, name, text, msg):
    p = Path(w) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="\n") as f:  # LF on Windows too, so a commit never rewrites other files
        f.write(text)
    git(w, "add", ".")
    git(w, "commit", "-q", "-m", msg)


def repo():
    base = Path(tempfile.mkdtemp(prefix="dl241-")).resolve()
    git(base, "init", "-q", "--bare", "-b", "main", "origin.git")
    git(base, "clone", "-q", str(base / "origin.git"), "app1")
    w = base / "app1"
    git(w, "config", "core.autocrlf", "false")
    commit(w, "a.txt", "a\n", "first")
    git(w, "push", "-q", "origin", "HEAD:main")
    git(w, "push", "-q", "origin", "HEAD:refs/heads/integ")
    return w


def branch(w, name, start, fname, text):
    git(w, "checkout", "-q", "-b", name, start)
    commit(w, fname, text, name)
    git(w, "push", "-q", "origin", name)


def siblings(w):
    branch(w, "contract", "origin/main", "api.txt", "api\n")
    for n in "ABC":
        branch(w, n, "contract", "sib-" + n + ".txt", n + "\n")  # not n + ".txt": A.txt is a.txt on Windows
    git(w, "checkout", "-q", "main")


def join(w, *args):
    return subprocess.run(["python3", str(JOIN), *args, "--no-gate"], cwd=w, env=ENV, capture_output=True, text=True)


class JoinSiblings(unittest.TestCase):
    def test_siblings_join_cleanly(self):
        w = repo()
        siblings(w)
        p = join(w, "--into", "integ", "A", "B", "C")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertNotIn("stacked", p.stderr)
        self.assertNotIn("skipped", p.stdout)

    def test_real_stacked_lists_files(self):
        w = repo()
        branch(w, "A", "origin/main", "x.txt", "1\n")
        branch(w, "B", "A", "y.txt", "1\n")
        git(w, "checkout", "-q", "A")
        commit(w, "x.txt", "2\n", "a2")
        git(w, "push", "-q", "origin", "A")
        git(w, "checkout", "-q", "main")
        p = join(w, "--into", "integ", "A", "B")
        self.assertIn("B is stacked on an older A; prefer B's side for files B rewrote", p.stderr)
        self.assertIn("files in both: x.txt", p.stderr)
        self.assertIn("skipped B: stacked on an older A, files: x.txt", p.stdout)
        self.assertEqual(p.returncode, 3)

    def test_skipped_lines_with_push(self):
        w = repo()
        siblings(w)
        branch(w, "D", "origin/main", "a.txt", "other\n")  # conflicts with main's a.txt change below
        git(w, "checkout", "-q", "main")
        git(w, "checkout", "-q", "-b", "integ2", "origin/integ")
        commit(w, "a.txt", "changed\n", "integ change")
        git(w, "push", "-q", "origin", "integ2:integ")
        git(w, "checkout", "-q", "main")
        p = join(w, "--into", "integ", "A", "D", "nope", "--push")
        self.assertIn("skipped D: conflict with integ in: a.txt", p.stdout)
        self.assertIn("skipped nope: missing on origin", p.stdout)
        self.assertIn("joined 1 of 3 branches; skipped: D, nope", p.stdout)
        self.assertEqual(p.returncode, 3)

    def test_partial_exit_codes(self):
        w = repo()
        siblings(w)
        p = join(w, "--into", "integ", "A", "nope")
        self.assertEqual(p.returncode, 5, p.stderr + p.stdout)
        self.assertIn("joined 1 of 2 branches; skipped: nope", p.stdout)
        w2 = repo()
        siblings(w2)
        q = join(w2, "--into", "integ", "A", "nope", "--allow-partial")
        self.assertEqual(q.returncode, 0, q.stderr + q.stdout)
        self.assertIn("joined 1 of 2 branches; skipped: nope", q.stdout)


if __name__ == "__main__":
    unittest.main()
