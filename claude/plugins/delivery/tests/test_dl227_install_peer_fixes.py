"""DL227: no compiled Python copied, a .gitignore block, indented prune list, ignored files not hinted."""
import os
import shutil
import sys
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import _helpers  # noqa: F401
import delivery_ci_install as INS

HERE = os.path.dirname(os.path.abspath(__file__))
PRUNE_DIR = os.path.join(os.path.dirname(HERE), "templates", "shared", "scripts", "delivery")


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = INS.main(list(argv))
    return code, out.getvalue() + err.getvalue()


def git(root, *a):
    return subprocess.run(["git", "-C", root] + list(a), capture_output=True, text=True)


class Dl227(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        git(self.tmp, "init", "-q")

    def p(self, rel):
        return os.path.join(self.tmp, rel)

    def install(self):
        return run("install", "--track", "ts", "--root", self.tmp)[1]

    def test_no_pyc_copied(self):
        fake = os.path.join(INS.TEMPLATES, "shared", "scripts", "delivery", "stale_dl227.pyc")
        with open(fake, "wb") as f:
            f.write(b"x")
        self.addCleanup(os.remove, fake)
        self.install()
        for d, _n, files in os.walk(self.tmp):
            self.assertNotIn("__pycache__", d)
            self.assertFalse([f for f in files if f.endswith(".pyc")])

    def test_gitignore_block_once(self):
        with open(self.p(".gitignore"), "wb") as f:
            f.write(b"node_modules/\r\n")
        self.install()
        self.install()
        data = open(self.p(".gitignore"), "rb").read().decode()
        self.assertEqual(data.count(INS.GI_BEGIN), 1)
        self.assertIn("node_modules/\r\n__pycache__/\r\n*.pyc\r\n", data.replace(INS.GI_BEGIN + "\r\n", ""))
        self.assertNotIn("\n" + "x", data.replace("\r\n", ""))

    def test_tracked_pyc_reported_not_removed(self):
        self.install()
        pyc = self.p("scripts/delivery/__pycache__/x.pyc")
        os.makedirs(os.path.dirname(pyc))
        open(pyc, "wb").write(b"x")
        git(self.tmp, "add", "-f", "scripts/delivery/__pycache__/x.pyc")
        out = self.install()
        self.assertIn("git rm --cached scripts/delivery/__pycache__/x.pyc", out)
        self.assertTrue(os.path.exists(pyc))
        self.assertIn("scripts/delivery/__pycache__/x.pyc", git(self.tmp, "ls-files").stdout)

    def test_indented_one_line_list(self):
        sys.path.insert(0, PRUNE_DIR)
        import artifact_prune as A
        for text in ('    workflows: ["CI", "E2E"]\n', '  workflows: ["CI", "E2E"]\r\n', '  workflows: [CI, E2E]\n'):
            new = A.render_workflows_text(text, ["X"])
            self.assertIn('workflows: ["X"]', new)
            self.assertEqual(new.endswith("\r\n"), text.endswith("\r\n"))

    def test_ignored_config_not_listed(self):
        with open(self.p(".gitignore"), "w") as f:
            f.write(".delivery/config.json\n")
        out = self.install()
        self.assertIn("ignored by .gitignore", out)
        listed = out.split("not in git yet (commit them):")[-1] if "not in git yet" in out else ""
        self.assertNotIn(".delivery/config.json", listed.split("ignored by")[0])


if __name__ == "__main__":
    unittest.main()
