"""DL201: update keeps a file the project changed, writes <file>.new and reports it."""
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import _helpers  # noqa: F401  (puts the plugin scripts on sys.path)
import delivery_ci_install as INS
import delivery_doctor as DOC

EDITED = "scripts/delivery/ci_watch.py"
UNTOUCHED = "scripts/delivery/join.py"


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = INS.main(list(argv))
    return code, out.getvalue() + err.getvalue()


class KeepAndReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # a private copy of the templates, so a test can change the "new" template
        self.tpl = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tpl, True)
        shutil.copytree(INS.TEMPLATES, os.path.join(self.tpl, "templates"))
        old = INS.TEMPLATES
        INS.TEMPLATES = os.path.join(self.tpl, "templates")
        self.addCleanup(setattr, INS, "TEMPLATES", old)

    def p(self, rel):
        return os.path.join(self.tmp, rel.replace("/", os.sep))

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def write(self, path, text):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def template(self, rel):
        for part in ("shared", "ts"):
            path = os.path.join(INS.TEMPLATES, part, rel.replace("/", os.sep))
            if os.path.exists(path):
                return path
        raise AssertionError(rel)

    def test_edited_file_kept_and_untouched_file_overwritten(self):
        self.assertEqual(run("install", "--track", "ts", "--root", self.tmp)[0], 0)
        self.assertTrue(os.path.exists(self.p(".delivery/ci-install-state.json")))
        self.write(self.p(EDITED), "# my edit\n")
        self.write(self.template(EDITED), "# new template\n")
        self.write(self.template(UNTOUCHED), "# new join\n")
        code, out = run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read(self.p(EDITED)), "# my edit\n")
        self.assertEqual(self.read(self.p(EDITED + ".new")), "# new template\n")
        self.assertIn("kept (project changes): %s; new template in %s.new; compare with: git diff --no-index %s %s.new"
                      % (EDITED, EDITED, EDITED, EDITED), out)
        self.assertIn("overwritten " + UNTOUCHED, out)
        self.assertEqual(self.read(self.p(UNTOUCHED)), "# new join\n")
        self.assertFalse(os.path.exists(self.p(UNTOUCHED + ".new")))
        self.assertNotIn("first update", out)                 # a record existed

    def test_no_state_file_keeps_a_differing_file(self):
        run("install", "--track", "ts", "--root", self.tmp)
        os.remove(self.p(".delivery/ci-install-state.json"))
        self.write(self.p(EDITED), "# old copy\n")
        code, out = run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read(self.p(EDITED)), "# old copy\n")
        self.assertTrue(os.path.exists(self.p(EDITED + ".new")))
        self.assertIn("first update", out)

    def test_later_update_replaces_old_new_file_and_dry_run_writes_nothing(self):
        run("install", "--track", "ts", "--root", self.tmp)
        self.write(self.p(EDITED), "# my edit\n")
        self.write(self.p(EDITED + ".new"), "stale\n")
        run("update", "--track", "ts", "--root", self.tmp, "--dry-run")
        self.assertEqual(self.read(self.p(EDITED + ".new")), "stale\n")
        run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(self.read(self.p(EDITED + ".new")), self.read(self.template(EDITED)))

    def test_doctor_warns_and_names_the_kept_file(self):
        run("install", "--track", "ts", "--root", self.tmp)
        self.write(self.p(EDITED), "# my edit\n")
        run("update", "--track", "ts", "--root", self.tmp)
        items = DOC.scripts_items(self.tmp)
        self.assertEqual(items[0]["status"], "warn")
        self.assertIn(EDITED, items[0]["detail"])
        self.assertIn(".new", items[0]["detail"])


if __name__ == "__main__":
    unittest.main()
