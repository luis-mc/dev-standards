"""DL154: the pre-push secret scan reads .gitleaksignore and .gitleaks.toml from the pushed commit."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "templates" / "shared" / "scripts" / "delivery"))
import fast_guards as F  # noqa: E402

RUN = "gitleaks git --log-opts=main..HEAD --redact --no-banner"
KEY = "AKIA" + "IOSFODNN7EXAMPLE"


def git(cwd, *a):
    return subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=t", *a],
                          cwd=str(cwd), capture_output=True, text=True, check=True).stdout.strip()


class Base(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        self.repo = self.d / "repo"
        self.repo.mkdir()
        self.tmp = self.d / "tmp"
        self.tmp.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "a.txt").write_text("x\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "one")

    def commit(self, name, text, msg):
        (self.repo / name).write_text(text)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", msg)
        return git(self.repo, "rev-parse", "HEAD")


class Command(Base):
    def flags(self, sha):
        return F.with_pushed_gitleaks([{"run": RUN}], self.repo, sha, self.tmp)[0]["run"]

    def ignore_text(self, run):
        path = run.split("--gitleaks-ignore-path \"")[1].split("\"")[0]
        return Path(path).read_text()

    def test_pushed_ignore_beats_dirty_tree_at_head(self):
        sha = self.commit(".gitleaksignore", "entry-in-commit\n", "two")
        (self.repo / ".gitleaksignore").write_text("entry-in-tree\n")  # dirty
        run = self.flags(sha)
        self.assertTrue(run.startswith(RUN))
        self.assertEqual(self.ignore_text(run), "entry-in-commit\n")

    def test_pushed_commit_not_head(self):
        sha = self.commit(".gitleaksignore", "entry-in-commit\n", "two")
        self.commit(".gitleaksignore", "entry-later\n", "three")
        self.assertEqual(self.ignore_text(self.flags(sha)), "entry-in-commit\n")

    def test_no_ignore_in_commit_gives_empty_file(self):
        sha = git(self.repo, "rev-parse", "HEAD")
        (self.repo / ".gitleaksignore").write_text("entry-in-tree\n")
        run = self.flags(sha)
        self.assertEqual(self.ignore_text(run), "")
        self.assertNotIn("--config", run)

    def test_config_from_commit(self):
        sha = self.commit(".gitleaks.toml", "title = \"x\"\n", "two")
        run = self.flags(sha)
        self.assertIn("--config", run)

    def test_other_steps_untouched(self):
        sha = git(self.repo, "rev-parse", "HEAD")
        out = F.with_pushed_gitleaks([{"run": "pnpm test"}], self.repo, sha, self.tmp)
        self.assertEqual(out[0]["run"], "pnpm test")


@unittest.skipUnless(shutil.which("gitleaks"), "gitleaks is not installed")
class Real(Base):
    """A branch that carries its own ignore entry passes although the tree lacks it."""

    def scan(self, sha, dirty=None):
        if dirty is not None:
            (self.repo / ".gitleaksignore").write_text(dirty)
        run = F.with_pushed_gitleaks([{"run": "gitleaks git --log-opts=main..%s --no-banner" % sha}],
                                     self.repo, sha, self.tmp)[0]["run"]
        return subprocess.run(run, shell=True, cwd=str(self.repo), capture_output=True, text=True).returncode

    def test_ignore_in_commit(self):
        git(self.repo, "checkout", "-qb", "feat")
        sha = self.commit("k.txt", "aws_access_key_id = %s\n" % KEY, "leak")
        fp = git(self.repo, "log", "-1", "--format=%H").strip()
        self.assertNotEqual(self.scan(sha), 0)
        entry = "%s:k.txt:aws-access-token:1\n" % fp
        sha2 = self.commit(".gitleaksignore", entry, "ignore")
        self.assertEqual(self.scan(sha2, dirty=""), 0)


if __name__ == "__main__":
    unittest.main()
