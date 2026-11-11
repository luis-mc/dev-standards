"""DL197: the join's docs strip keeps the base's docs/work files and removes only what the branches added."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
JOIN = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery" / "join.py"
DOCS_WORK = ROOT / "claude" / "plugins" / "docs" / "scripts" / "docs_work.py"
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com", LUISMC_DOCS_WORK=str(DOCS_WORK))


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, env=ENV, check=True, capture_output=True, text=True).stdout


def write(w, name, text):
    p = Path(w) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def repo(base_has_work):
    base = Path(tempfile.mkdtemp(prefix="dl197-")).resolve()
    git(base, "init", "-q", "--bare", "-b", "main", "origin.git")
    git(base, "clone", "-q", str(base / "origin.git"), "app1")
    w = base / "app1"
    write(w, "a.txt", "a\n")
    if base_has_work:
        write(w, "docs/work/agents/keep.txt", "base\n")
    git(w, "add", ".")
    git(w, "commit", "-q", "-m", "first")
    git(w, "push", "-q", "origin", "HEAD:main")
    git(w, "push", "-q", "origin", "HEAD:refs/heads/integ")
    git(w, "checkout", "-q", "-b", "f1")
    write(w, "docs/work/DL1/REPORT.md", "# DL1\n\nSummary: done\n")
    if base_has_work:
        write(w, "docs/work/agents/keep.txt", "edited\n")
    write(w, "b.txt", "b\n")
    git(w, "add", ".")
    git(w, "commit", "-q", "-m", "work")
    git(w, "push", "-q", "origin", "f1")
    git(w, "checkout", "-q", "main")
    return w


def join(w):
    return subprocess.run(["python3", str(JOIN), "--into", "integ", "f1", "--no-gate"], cwd=w, env=ENV,
                          capture_output=True, text=True)


class KeepBaseDocsWork(unittest.TestCase):
    def test_base_file_kept_added_file_removed(self):
        w = repo(True)
        p = join(w)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((w / "docs/work/agents/keep.txt").read_text(), "base\n")
        self.assertFalse((w / "docs/work/DL1/REPORT.md").exists())
        self.assertTrue((w / "b.txt").exists())

    def test_no_base_docs_work_strips_all(self):
        w = repo(False)
        p = join(w)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse((w / "docs/work").exists())
        self.assertTrue((w / "b.txt").exists())


if __name__ == "__main__":
    unittest.main()
