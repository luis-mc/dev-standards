"""DL308: template_adopt status, diff and adopt on a temp project."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import _helpers  # noqa: F401
import delivery_ci_install as INS
import template_adopt as TA

REL = "scripts/delivery/rust_ci.py"
OTHER = ".githooks/pre-push"


def run(root, *argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = TA.main(list(argv) + ["--root", root])
    return code, out.getvalue() + err.getvalue()


@unittest.skipIf(shutil.which("git") is None, "needs git on PATH")
class Adopt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tpl = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tpl, True)
        self.src = os.path.join(self.tpl, "t.py")
        self.body = "".join("line %d\n" % i for i in range(1, 21))
        self.put(self.src, self.body)
        self.old = TA.installed
        TA.installed = lambda root: {REL: self.src}
        self.addCleanup(setattr, TA, "installed", self.old)
        self.put(self.ours_path(), self.body)
        self.put(INS.base_path(self.tmp, REL), self.body)

    def put(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="\n") as f:
            f.write(text)

    def get(self, path):
        with open(path, newline="") as f:
            return f.read()

    def ours_path(self):
        return os.path.join(self.tmp, REL.replace("/", os.sep))

    def status(self):
        return run(self.tmp, "status")[1]

    def edit(self, text, n, new):
        lines = text.splitlines(True)
        lines[n] = new + "\n"
        return "".join(lines)

    def test_same(self):
        self.assertIn("same", self.status())

    def test_template_changed(self):
        self.put(self.src, self.edit(self.body, 2, "T"))
        self.assertIn("template-changed", self.status())

    def test_project_changed(self):
        self.put(self.ours_path(), self.edit(self.body, 2, "P"))
        self.assertIn("project-changed", self.status())

    def test_both_changed(self):
        self.put(self.src, self.edit(self.body, 2, "T"))
        self.put(self.ours_path(), self.edit(self.body, 15, "P"))
        self.assertIn("both-changed", self.status())

    def test_missing(self):
        os.remove(self.ours_path())
        self.assertIn("missing", self.status())

    def test_adopt_copies_and_updates_base(self):
        new = self.edit(self.body, 2, "T")
        self.put(self.src, new)
        code, _ = run(self.tmp, "adopt", REL)
        self.assertEqual(code, 0)
        self.assertEqual(self.get(self.ours_path()), new)
        self.assertEqual(self.get(INS.base_path(self.tmp, REL)), new)

    def test_clean_merge(self):
        self.put(self.src, self.edit(self.body, 2, "T"))
        self.put(self.ours_path(), self.edit(self.body, 15, "P"))
        code, _ = run(self.tmp, "adopt", REL)
        self.assertEqual(code, 0)
        got = self.get(self.ours_path())
        self.assertIn("T\n", got)
        self.assertIn("P\n", got)
        self.assertEqual(self.get(INS.base_path(self.tmp, REL)), self.get(self.src))

    def conflict(self):
        self.put(self.src, self.edit(self.body, 5, "T"))
        self.put(self.ours_path(), self.edit(self.body, 5, "P"))
        return self.get(self.ours_path())

    def test_conflict_changes_nothing(self):
        before = self.conflict()
        code, out = run(self.tmp, "adopt", REL)
        self.assertEqual(code, 1)
        self.assertEqual(self.get(self.ours_path()), before)
        self.assertEqual(self.get(INS.base_path(self.tmp, REL)), self.body)
        self.assertIn("conflict", out)

    def test_write_conflicts(self):
        self.conflict()
        code, _ = run(self.tmp, "adopt", REL, "--write-conflicts")
        self.assertEqual(code, 1)
        self.assertIn("<<<<<<<", self.get(self.ours_path()))

    def test_dry_run_writes_nothing(self):
        self.put(self.src, self.edit(self.body, 2, "T"))
        code, out = run(self.tmp, "adopt", REL, "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.get(self.ours_path()), self.body)
        self.assertEqual(self.get(INS.base_path(self.tmp, REL)), self.body)

    def test_missing_base_recorded(self):
        os.remove(INS.base_path(self.tmp, REL))
        self.put(self.ours_path(), self.edit(self.body, 2, "P"))
        out = self.status()
        self.assertIn("no base was stored", out)
        self.assertEqual(self.get(INS.base_path(self.tmp, REL)), self.body)

    def test_diff(self):
        self.put(self.src, self.edit(self.body, 2, "T"))
        self.put(self.ours_path(), self.edit(self.body, 15, "P"))
        code, out = run(self.tmp, "diff", REL)
        self.assertEqual(code, 0)
        self.assertIn("+T", out)
        self.assertIn("+P", out)

    def test_all_lists_the_rest(self):
        self.conflict()
        code, out = run(self.tmp, "adopt", "--all")
        self.assertEqual(code, 1)
        self.assertIn("left for you", out)

    def test_unlisted_path_refused(self):
        code, _ = run(self.tmp, "adopt", "README.md")
        self.assertEqual(code, 2)


@unittest.skipIf(shutil.which("git") is None, "needs git on PATH")
class RealList(unittest.TestCase):
    def test_installed_list_from_templates(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        os.makedirs(os.path.join(tmp, ".delivery"))
        with open(os.path.join(tmp, ".delivery", "config.json"), "w") as f:
            json.dump({"track": "rust"}, f)
        items = TA.installed(tmp)
        self.assertIn(REL, items)
        self.assertNotIn(".delivery/config.json", items)


if __name__ == "__main__":
    unittest.main()
