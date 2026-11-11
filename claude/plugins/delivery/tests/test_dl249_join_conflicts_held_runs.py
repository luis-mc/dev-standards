"""DL249: join conflict line lists files; generated docs conflicts are rebuilt; held runs are recorded as held."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIR = HERE.parent / "templates" / "shared" / "scripts" / "delivery"
JOIN = DIR / "join.py"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(DIR))

FAKE_INDEX = ("import sys\nfrom pathlib import Path\n"
              "root = Path(sys.argv[sys.argv.index('--root') + 1])\n"
              "(root / 'docs' / 'docs-map.json').write_text('{\"rebuilt\": true}\\n')\n")


def make_env(tool_dir):
    return dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
                LUISMC_DOCS_WORK=str(Path(tool_dir) / "docs_work.py"))


def git(cwd, env, *a):
    return subprocess.run(["git", *a], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def write_commit(w, env, files, msg):
    for name, text in files.items():
        p = Path(w) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    git(w, env, "add", ".")
    git(w, env, "commit", "-q", "-m", msg)


def conflict_repo(branch_files):
    """main and DL9-feat both change docs/docs-map.json (and the branch changes branch_files too)."""
    base = Path(tempfile.mkdtemp(prefix="dl249-")).resolve()
    tools = base / "tools"
    tools.mkdir()
    (tools / "docs_index.py").write_text(FAKE_INDEX)
    (tools / "docs_work.py").write_text("")
    env = make_env(tools)
    git(base, env, "init", "-q", "--bare", "-b", "main", "origin.git")
    git(base, env, "clone", "-q", str(base / "origin.git"), "app1")
    w = base / "app1"
    write_commit(w, env, {"docs/docs-map.json": "{}\n", "src.txt": "one\n"}, "first")
    git(w, env, "push", "-q", "origin", "HEAD:main")
    git(w, env, "checkout", "-q", "-b", "DL9-feat")
    write_commit(w, env, dict(branch_files, **{"docs/docs-map.json": '{"b": 1}\n'}), "feat")
    git(w, env, "push", "-q", "origin", "DL9-feat")
    git(w, env, "checkout", "-q", "main")
    write_commit(w, env, {"docs/docs-map.json": '{"m": 1}\n', "src.txt": "one\nmain\n"}, "main change")
    git(w, env, "push", "-q", "origin", "main")
    return w, env


def run_join(w, env):
    return subprocess.run([sys.executable, str(JOIN), "--into", "integ", "--create", "DL9-feat", "--no-gate"],
                          cwd=w, env=env, capture_output=True, text=True)


class JoinConflictTests(unittest.TestCase):
    def test_generated_docs_only_is_rebuilt(self):
        w, env = conflict_repo({})
        p = run_join(w, env)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertIn("conflicts only in generated docs", p.stdout)
        self.assertEqual((w / "docs" / "docs-map.json").read_text().strip(), '{"rebuilt": true}')
        self.assertIn("DL9-feat", git(w, env, "log", "--format=%s", "integ"))

    def test_generated_plus_source_stays_conflict_and_lists_files(self):
        w, env = conflict_repo({"src.txt": "one\nbranch\n"})
        p = run_join(w, env)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("DL9-feat conflicts with integ in:\n    docs/docs-map.json\n    src.txt", p.stderr)
        self.assertIn("conflict with integ in: docs/docs-map.json, src.txt", p.stderr + p.stdout)

    def test_helpers(self):
        import join
        self.assertTrue(join.is_generated_doc("docs/reference/x/y.md"))
        self.assertTrue(join.is_generated_doc("docs\\index.html"))
        self.assertFalse(join.is_generated_doc("docs/features/a/spec.md"))
        self.assertEqual(join.conflict_files([]), ["(files unknown)"])
        self.assertEqual(join.conflict_files(None), ["(files unknown)"])
        self.assertEqual(join.conflict_files(["a"]), ["a"])


class HeldRunTests(unittest.TestCase):
    def test_held_run_is_recorded_as_held(self):
        import test_watch as T
        L = T.L
        root = T.make_root()
        T.seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        r = T.routes_for_green()
        r[("gh", "run", "list", "--commit")] = (0, T.runs((1, "in_progress", None, T.SHA, "release/29")))
        r[("gh", "run", "list", "--status")] = (0, T.runs((50, "in_progress", None, "c" * 40, "feature/x")))
        r[("gh", "run", "cancel")] = (0, "")
        T.watcher(root, T.FakeShell(r)).run_once()
        held = L.load(root)["held_runs"]
        self.assertEqual([(h["id"], h["state"]) for h in held], [(50, "held")])


if __name__ == "__main__":
    unittest.main()
