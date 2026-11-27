import contextlib
import io
import unittest
from pathlib import Path
from _helpers import *  # noqa
import docs_work as K


def work_repo():
    d = project({"docs/features/a/spec.md": spec(fid="a")})
    git(d, "add", "-A"); git(d, "commit", "-q", "-m", "base")
    w(d, "docs/work/reports/T9.md", "# T9\n\nSummary: x.\n")
    w(d, "docs/work/p.md", "x")
    git(d, "add", "-A"); git(d, "commit", "-q", "-m", "work")
    return d


class StripPrintsTheCommitTests(unittest.TestCase):
    """C4 (DS304): strip --apply removes docs/work/ from the working tree and prints the commit; it runs no git write."""

    def run_strip(self, d):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = K.main(["strip", "--root", str(d), "--apply", "--base", "main"])
        return rc, out.getvalue()

    def test_strip_apply_writes_no_git_state_and_prints_the_commit(self):
        d = work_repo()
        head = git(d, "rev-parse", "HEAD").stdout.strip()
        rc, out = self.run_strip(d)
        self.assertEqual(rc, 0)
        self.assertFalse((d / "docs/work").exists())
        self.assertEqual(git(d, "rev-parse", "HEAD").stdout.strip(), head, "no commit")
        self.assertEqual(git(d, "diff", "--cached", "--name-only").stdout.strip(), "", "nothing staged")
        self.assertIn('git commit -m "Strip docs/work/ before the join (2 file(s))" -- docs/work', out)

    def test_the_printed_command_records_the_strip_and_keeps_other_staged_changes(self):
        d = work_repo()
        w(d, "other.txt", "o")
        git(d, "add", "other.txt")
        _rc, out = self.run_strip(d)
        cmd = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("git commit")][0]
        self.assertEqual(git(d, "diff", "--cached", "--name-only").stdout.strip(), "other.txt")
        msg = cmd.split('"')[1]
        git(d, "commit", "-q", "-m", msg, "--", "docs/work")
        self.assertEqual(git(d, "ls-files", "docs/work").stdout.strip(), "")
        self.assertEqual(git(d, "diff", "--cached", "--name-only").stdout.strip(), "other.txt")
        self.assertEqual(K.main(["guard", "--root", str(d), "--base", "main~1"]), 0)

    def test_untracked_work_needs_no_commit(self):
        d = project({"docs/features/a/spec.md": spec(fid="a")})
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "base")
        w(d, "docs/work/p.md", "x")
        rc, out = self.run_strip(d)
        self.assertEqual(rc, 0)
        self.assertIn("no commit needed", out)
        self.assertNotIn("git commit", out)

    def test_script_runs_no_git_write(self):
        src = (Path(K.__file__)).read_text(encoding="utf-8")
        for verb in ('"rm"', '"commit"', '"add"'):
            self.assertNotIn('D.git(root, ' + verb, src)


if __name__ == "__main__":
    unittest.main()
