import unittest
from _helpers import *  # noqa
import docs_work as K
import docs_lib as D


class WorkTests(unittest.TestCase):
    def repo(self):
        d = project({"docs/features/a/spec.md": spec(fid="a")})
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "base")
        git(d, "checkout", "-q", "-b", "agent")
        w(d, "docs/work/reports/DOC2.md", "# DOC2 report\n\nStatus: READY\n\nBuilt the plugin. More text.\n")
        w(d, "docs/work/reports/T9.md", "# T9\n\nSummary: fixed the thing.\n")
        w(d, "docs/work/prompts/p.md", "x")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "work")
        return d

    def test_guard_fails_when_work_files_are_added(self):
        d = self.repo()
        self.assertEqual(K.main(["guard", "--root", str(d), "--base", "main"]), 1)

    def test_guard_passes_without_work_files(self):
        d = project()
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "base")
        git(d, "checkout", "-q", "-b", "agent")
        w(d, "docs/guides/g.md", "# G\n")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "g")
        self.assertEqual(K.main(["guard", "--root", str(d), "--base", "main"]), 0)

    def test_guard_allows_work_files_already_on_base(self):
        d = project({"docs/work/old.md": "x"})
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "base")
        git(d, "checkout", "-q", "-b", "agent")
        w(d, "docs/work/old.md", "changed")
        git(d, "add", "-A"); git(d, "commit", "-q", "-m", "edit")
        self.assertEqual(K.main(["guard", "--root", str(d), "--base", "main"]), 0)

    def test_summaries(self):
        d = self.repo()
        s = K.summaries(d)
        self.assertEqual(s[0], "- DOC2: Status: READY. Built the plugin.")
        self.assertEqual(s[1], "- T9: fixed the thing.")

    def test_strip_dry_run_then_apply(self):
        d = self.repo()
        K.main(["strip", "--root", str(d)])
        self.assertTrue((d / "docs/work/reports/DOC2.md").is_file())
        K.main(["strip", "--root", str(d), "--apply"])
        self.assertFalse((d / "docs/work").exists())
        self.assertEqual(git(d, "ls-files", "docs/work").stdout.strip(), "")
        self.assertTrue((d / "docs/features/a/spec.md").is_file(), "lasting docs untouched")
        self.assertEqual(K.main(["guard", "--root", str(d), "--base", "main"]), 1, "index still holds the removal until committed? added files are measured on HEAD")


if __name__ == "__main__":
    unittest.main()
