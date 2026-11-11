"""DL225 join fixes: new --into branch, origin/X stripped, default integration name, Cargo.lock path."""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
JOIN = DIR / "join.py"
GUARD = DIR / "session_guard.py"
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com", LUISMC_DOCS_WORK="/nonexistent/docs_work.py")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, env=ENV, check=True, capture_output=True, text=True).stdout


def commit(w, name, text, msg):
    p = Path(w) / name
    p.write_text(text)
    git(w, "add", ".")
    git(w, "commit", "-q", "-m", msg)


def repo():
    base = Path(tempfile.mkdtemp(prefix="dl225-")).resolve()
    git(base, "init", "-q", "--bare", "-b", "main", "origin.git")
    git(base, "clone", "-q", str(base / "origin.git"), "app1")
    w = base / "app1"
    commit(w, "a.txt", "a\n", "first")
    git(w, "push", "-q", "origin", "HEAD:main")
    git(w, "checkout", "-q", "-b", "DL9-feat")
    commit(w, "f.txt", "f\n", "feat")
    git(w, "push", "-q", "origin", "DL9-feat")
    git(w, "checkout", "-q", "main")
    return w


def join(w, *args):
    return subprocess.run([sys.executable, str(JOIN), *args, "--no-gate"], cwd=w, env=ENV, capture_output=True, text=True)


def remote_branches(w):
    return git(w, "ls-remote", "--heads", "origin")


def load_join():
    sys.path.insert(0, str(DIR))
    spec = importlib.util.spec_from_file_location("join_dl225", JOIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class JoinPeerFixes(unittest.TestCase):
    def test_new_into_created_and_pushed(self):
        w = repo()
        p = join(w, "--into", "brand-new", "DL9-feat", "--push")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertIn("refs/heads/brand-new", remote_branches(w))
        self.assertIn("f.txt", git(w, "ls-tree", "-r", "--name-only", "origin/brand-new"))

    def test_origin_prefix_stripped(self):
        w = repo()
        p = join(w, "--into", "integ", "origin/DL9-feat", "--create")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertIn("f.txt", git(w, "ls-tree", "-r", "--name-only", "integ"))

    def test_default_integration_name(self):
        w = repo()
        p = join(w, "DL9-feat", "--push")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertIn("refs/heads/DL9-integration", remote_branches(w))

    def test_names(self):
        j = load_join()
        self.assertEqual(j.default_integration(["DL225-join-fixes", "DL1-x"]), "DL225-integration")
        self.assertEqual(j.default_integration(["fix-thing"]), "fix-integration")
        self.assertEqual(j.strip_remote("origin/X/y", ["origin", "up"]), "X/y")
        self.assertEqual(j.strip_remote("feature/x", ["origin"]), "feature/x")

    def test_cargo_decision_logic(self):
        j = load_join()
        calls = []

        def runner(ok):
            def run(cmd, cwd):
                calls.append(cmd)
                return (0 if cmd in ok else 1), 0.0
            return run

        self.assertIn("not installed", j.resolve_cargo_lock(Path("."), "Cargo.lock", runner(set()), lambda _: None))
        self.assertIn("Cargo.lock", j.resolve_cargo_lock(Path("."), "Cargo.lock", runner(set()), lambda _: None))
        calls.clear()
        ok = {"cargo fetch", "cargo fetch --locked"}
        self.assertIsNone(j.resolve_cargo_lock(Path("."), "Cargo.lock", runner(ok), lambda _: "cargo"))
        self.assertEqual(calls, ["cargo fetch", "cargo fetch --locked"])
        calls.clear()
        # fetch leaves the lock short: --locked fails first, update -w is tried, still failing
        self.assertIn("still not complete",
                      j.resolve_cargo_lock(Path("."), "Cargo.lock", runner({"cargo fetch"}), lambda _: "cargo"))
        self.assertIn("cargo update -w", calls)
        self.assertTrue(j.is_cargo_lock("crates/Cargo.lock"))
        self.assertFalse(j.is_cargo_lock("pnpm-lock.yaml"))

    @unittest.skipIf(shutil.which("cargo") is None, "cargo is not installed")
    def test_cargo_conflict_real(self):
        base = Path(tempfile.mkdtemp(prefix="dl225c-")).resolve()
        w = base / "p"
        w.mkdir()
        git(w, "init", "-q", "-b", "main")
        (w / "src").mkdir()
        (w / "src" / "lib.rs").write_text("")
        (w / "Cargo.toml").write_text('[package]\nname = "p"\nversion = "0.1.0"\nedition = "2021"\n')
        git(w, "add", ".")
        git(w, "commit", "-q", "-m", "init")
        subprocess.run(["cargo", "generate-lockfile", "--offline"], cwd=w, check=True, capture_output=True)
        j = load_join()
        # Offline smoke: no crates to add, so fetch and --locked both pass on a regenerated lock.
        subprocess.run(["cargo", "generate-lockfile", "--offline"], cwd=w, check=True, capture_output=True)
        self.assertIsNone(j.resolve_cargo_lock(w, "Cargo.lock"))

    def test_guard_message_names_convention(self):
        text = GUARD.read_text(encoding="utf-8")
        self.assertIn("<task>-integration", text)
        self.assertIn("join.py --into <task>-integration --create", text)


if __name__ == "__main__":
    unittest.main()
