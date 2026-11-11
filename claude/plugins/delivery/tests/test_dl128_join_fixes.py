"""DL128 join fixes: stacked branches, --create, mock note, local-ahead build, docs/work conflicts."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

JOIN = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery" / "join.py"
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com", LUISMC_DOCS_WORK="/nonexistent/docs_work.py")


def git(cwd, *a, check=True):
    return subprocess.run(["git", *a], cwd=cwd, env=ENV, check=check, capture_output=True, text=True).stdout


def commit(w, name, text, msg):
    p = Path(w) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    git(w, "add", ".")
    git(w, "commit", "-q", "-m", msg)


def repo():
    base = Path(tempfile.mkdtemp(prefix="dl128-")).resolve()
    git(base, "init", "-q", "--bare", "-b", "main", "origin.git")
    w = base / "app1"
    git(base, "clone", "-q", str(base / "origin.git"), "app1")
    commit(w, "a.txt", "a\n", "first")
    git(w, "push", "-q", "origin", "HEAD:main")
    git(w, "push", "-q", "origin", "HEAD:refs/heads/integ")
    return w


def join(w, *args):
    return subprocess.run(["python3", str(JOIN), *args, "--no-gate"], cwd=w, env=ENV, capture_output=True, text=True)


class JoinFixes(unittest.TestCase):
    def test_missing_integration_needs_create(self):
        w = repo()
        git(w, "checkout", "-q", "-b", "nope")
        commit(w, "n.txt", "n\n", "n")
        git(w, "checkout", "-q", "main")  # DL225: a branch that is only local still needs --create
        p = join(w, "--into", "nope", "x")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--create", p.stderr)
        self.assertIn("git push origin origin/main:refs/heads/nope", p.stderr)

    def test_create_pushes_default(self):
        w = repo()
        git(w, "checkout", "-q", "-b", "f1")
        commit(w, "f.txt", "f\n", "f")
        git(w, "push", "-q", "origin", "f1")
        git(w, "checkout", "-q", "main")
        p = join(w, "--into", "newint", "f1", "--create")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertIn("created newint", p.stdout)
        self.assertIn("refs/heads/newint", git(w, "ls-remote", "origin", "newint"))

    def test_stacked_branch_stops(self):
        w = repo()
        git(w, "checkout", "-q", "-b", "A", "origin/main")
        commit(w, "x.txt", "1\n", "a1")
        git(w, "push", "-q", "origin", "A")
        git(w, "checkout", "-q", "-b", "B")
        commit(w, "y.txt", "1\n", "b1")
        git(w, "push", "-q", "origin", "B")
        git(w, "checkout", "-q", "A")
        commit(w, "x.txt", "2\n", "a2")
        git(w, "push", "-q", "origin", "A")
        git(w, "checkout", "-q", "main")
        p = join(w, "--into", "integ", "A", "B")
        self.assertIn("B is stacked on an older A; prefer B's side for files B rewrote", p.stderr)
        self.assertNotEqual(p.returncode, 0)

    def test_local_ahead_is_kept(self):
        w = repo()
        for n in ("f1", "f2"):
            git(w, "checkout", "-q", "-b", n, "origin/main")
            commit(w, n + ".txt", n, n)
            git(w, "push", "-q", "origin", n)
        git(w, "checkout", "-q", "main")
        self.assertEqual(join(w, "--into", "integ", "f1").returncode, 0)
        p = join(w, "--into", "integ", "f2")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("building on the local branch", p.stdout)
        log = git(w, "log", "--format=%s", "integ")
        self.assertIn("Join f1", log)
        self.assertIn("Join f2", log)

    def test_diverged_local_is_refused(self):
        w = repo()
        git(w, "checkout", "-q", "-B", "integ", "origin/integ")
        commit(w, "l.txt", "l", "local only")
        git(w, "checkout", "-q", "-b", "o", "origin/integ")
        commit(w, "o.txt", "o", "other")
        git(w, "push", "-q", "origin", "o:integ")
        git(w, "checkout", "-q", "main")
        p = join(w, "--into", "integ", "main")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("would lose them", p.stderr)

    def test_docs_work_conflict_resolves(self):
        w = repo()
        for n, t in (("f1", "one"), ("f2", "two")):
            git(w, "checkout", "-q", "-b", n, "origin/main")
            commit(w, "docs/work/T/REPORT.md", t, n)
            git(w, "push", "-q", "origin", n)
        git(w, "checkout", "-q", "main")
        p = join(w, "--into", "integ", "f1", "f2")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertIn("under docs/work/", p.stdout)

    def test_pre_pr_docs_never_changes_exit(self):
        """DL140: failing or missing docs scripts do not change the exit code, and the join result is still written."""
        import json
        w = repo()
        git(w, "checkout", "-q", "-b", "f1", "origin/main")
        commit(w, "f.txt", "f\n", "f")
        git(w, "push", "-q", "origin", "f1")
        git(w, "checkout", "-q", "main")
        scripts = Path(tempfile.mkdtemp(prefix="dl128-docs-"))
        for n in ("docs_index.py", "docs_check.py"):
            (scripts / n).write_text("import sys\nsys.exit(1)\n")
        env = dict(ENV, LUISMC_DOCS_WORK=str(scripts / "docs_work.py"))
        p = subprocess.run(["python3", str(JOIN), "--into", "integ", "f1", "--no-gate"], cwd=w, env=env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        res = json.loads((w / ".delivery" / "join-result.json").read_text())
        self.assertEqual(res["joined"], ["f1"])
        self.assertIn("failed", res["pre_pr_docs"]["steps"]["docs index build"])
        # absent scripts: same exit code, and the output does not say "skipped" (the gate-skip text)
        p = join(w, "--into", "integ", "f1")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertNotIn("skipped", p.stdout)

    def test_mock_note(self):
        import sys
        sys.path.insert(0, str(JOIN.parent))
        sys.dont_write_bytecode = True
        import join as j
        import delivery_common as dc
        root = Path(tempfile.mkdtemp())
        self.assertIsNone(j.mock_interaction_note(root))
        d = root / dc.LOG_DIR / "join"
        d.mkdir(parents=True)
        (d / "e2e.log").write_text("Error: Unhandled API call GET /x\n")
        self.assertIn("join-interaction failure", j.mock_interaction_note(root))


if __name__ == "__main__":
    unittest.main()
