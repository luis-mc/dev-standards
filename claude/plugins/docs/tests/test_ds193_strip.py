import os
import stat
import unittest
from _helpers import *  # noqa
import docs_work as K


def work_repo():
    d = project({"docs/features/a/spec.md": spec(fid="a")})
    git(d, "add", "-A"); git(d, "commit", "-q", "-m", "base")
    w(d, "docs/work/reports/T9.md", "# T9\n\nSummary: x.\n")
    w(d, "docs/work/p.md", "x")
    git(d, "add", "-A"); git(d, "commit", "-q", "-m", "work")
    return d


class StripCommitTests(unittest.TestCase):
    def test_strip_apply_commits_and_leaves_nothing_staged(self):
        d = work_repo()
        self.assertEqual(K.main(["strip", "--root", str(d), "--apply", "--base", "main"]), 0)
        self.assertFalse((d / "docs/work").exists())
        self.assertEqual(git(d, "diff", "--cached", "--name-only").stdout.strip(), "")
        self.assertIn("Strip docs/work/", git(d, "log", "-1", "--format=%s").stdout)
        self.assertEqual(git(d, "ls-files", "docs/work").stdout.strip(), "")

    def test_other_staged_changes_stay_staged(self):
        d = work_repo()
        w(d, "other.txt", "o")
        git(d, "add", "other.txt")
        self.assertEqual(K.main(["strip", "--root", str(d), "--apply"]), 0)
        self.assertEqual(git(d, "diff", "--cached", "--name-only").stdout.strip(), "other.txt")

    @unittest.skipIf(os.name == "nt", "hook mode bits")
    def test_failed_commit_exits_nonzero_and_names_the_fix(self):
        d = work_repo()
        hook = d / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = K.main(["strip", "--root", str(d), "--apply"])
        self.assertEqual(rc, 1)
        self.assertIn("still staged", err.getvalue())
        self.assertIn("git commit -m", err.getvalue())
        self.assertNotEqual(git(d, "diff", "--cached", "--name-only").stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
