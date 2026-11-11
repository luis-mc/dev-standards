"""DL255: update keeps the project's artifact-prune list; template additions are appended once."""
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import _helpers  # noqa: F401
import delivery_ci_install as INS

WF = ".github/workflows/artifact-prune.yml"
DEFAULT = '["CI", "Package"]'


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = INS.main(list(argv))
    return code, out.getvalue() + err.getvalue()


class PruneListMerge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tpl = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tpl, True)
        shutil.copytree(INS.TEMPLATES, os.path.join(self.tpl, "templates"))
        old = INS.TEMPLATES
        INS.TEMPLATES = os.path.join(self.tpl, "templates")
        self.addCleanup(setattr, INS, "TEMPLATES", old)
        self.twf = os.path.join(INS.TEMPLATES, "shared", WF.replace("/", os.sep))
        self.assertEqual(run("install", "--track", "ts", "--root", self.tmp)[0], 0)

    def read(self, path):
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()

    def write(self, path, text):
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)

    @property
    def pwf(self):
        return os.path.join(self.tmp, WF.replace("/", os.sep))

    def names(self, path=None):
        return INS.prune_names(self.read(path or self.pwf))

    def set_tpl(self, line=None, extra=None):
        text = self.read(self.twf)
        if line:
            text = text.replace(DEFAULT, line)
        if extra:
            text = extra + text      # the template edits the top, the project the bottom
        self.write(self.twf, text)

    def set_proj(self, line=None, extra=None):
        text = self.read(self.pwf)
        if line:
            text = text.replace(DEFAULT, line)
        if extra:
            text = text + extra
        self.write(self.pwf, text)

    def update(self):
        code, out = run("update", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        return out

    def test_project_extra_names_kept(self):
        self.set_proj('["CI", "Package", "E2E"]')
        self.set_tpl(extra="# template note\n")
        self.update()
        self.assertEqual(self.names(), ["CI", "Package", "E2E"])

    def test_project_names_kept_when_file_unchanged_since_sync(self):
        self.set_proj('["CI", "E2E"]')
        self.update()          # records the file as the project's
        self.set_tpl(extra="# template note\n")
        out = self.update()
        self.assertEqual(self.names(), ["CI", "E2E"])
        self.assertIn("artifact-prune list: kept", out)

    def test_template_adds_name_appended_once(self):
        self.set_proj('["CI", "E2E"]')
        self.set_tpl('["CI", "Package", "Installers"]')
        out = self.update()
        self.assertEqual(self.names(), ["CI", "E2E", "Installers"])
        self.assertIn("Installers", out)
        self.update()
        self.assertEqual(self.names(), ["CI", "E2E", "Installers"])

    def test_removed_name_stays_removed(self):
        self.set_proj('["CI"]')
        self.update()
        self.assertEqual(self.names(), ["CI"])
        self.set_tpl(extra="# another note\n")
        self.update()
        self.assertEqual(self.names(), ["CI"])
        self.update()
        self.assertEqual(self.names(), ["CI"])

    def test_both_sides_change_other_lines(self):
        self.set_proj('["CI", "E2E"]', extra="# project line\n")
        self.set_tpl('["CI", "Package", "Installers"]', extra="# template line\n")
        out = self.update()
        text = self.read(self.pwf)
        self.assertIn("# project line", text)
        self.assertIn("# template line", text)
        self.assertEqual(self.names(), ["CI", "E2E", "Installers"])
        self.assertNotIn("<<<<<<<", text)
        self.assertFalse(os.path.exists(self.pwf + ".new"), out)

    def test_idempotent(self):
        self.set_proj('["CI", "E2E"]', extra="# project line\n")
        self.set_tpl('["CI", "Package", "Installers"]')
        self.update()
        first = self.read(self.pwf)
        self.update()
        self.assertEqual(self.read(self.pwf), first)


if __name__ == "__main__":
    unittest.main()
