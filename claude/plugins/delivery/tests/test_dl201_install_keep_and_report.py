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
        shutil.rmtree(self.p(".delivery/ci-install-base"))   # no base: the step-1 path
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
        shutil.rmtree(self.p(".delivery/ci-install-base"))
        self.write(self.p(EDITED), "# old copy\n")
        code, out = run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read(self.p(EDITED)), "# old copy\n")
        self.assertTrue(os.path.exists(self.p(EDITED + ".new")))
        self.assertIn("first update", out)

    def test_later_update_replaces_old_new_file_and_dry_run_writes_nothing(self):
        run("install", "--track", "ts", "--root", self.tmp)
        shutil.rmtree(self.p(".delivery/ci-install-base"))
        self.write(self.p(EDITED), "# my edit\n")
        self.write(self.p(EDITED + ".new"), "stale\n")
        run("update", "--track", "ts", "--root", self.tmp, "--dry-run")
        self.assertEqual(self.read(self.p(EDITED + ".new")), "stale\n")
        run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(self.read(self.p(EDITED + ".new")), self.read(self.template(EDITED)))

    def test_doctor_warns_and_names_the_kept_file(self):
        run("install", "--track", "ts", "--root", self.tmp)
        shutil.rmtree(self.p(".delivery/ci-install-base"))
        self.write(self.p(EDITED), "# my edit\n")
        run("update", "--track", "ts", "--root", self.tmp)
        items = DOC.scripts_items(self.tmp)
        self.assertEqual(items[0]["status"], "warn")
        self.assertIn(EDITED, items[0]["detail"])
        self.assertIn(".new", items[0]["detail"])

    # ---- step 2: 3-way merge ----
    def base_lines(self):
        return "".join("line %d\n" % i for i in range(1, 11))

    def install_with(self, text, crlf=False):
        self.write(self.template(EDITED), text)
        run("install", "--track", "ts", "--root", self.tmp)
        if crlf:
            with open(self.p(EDITED), "wb") as f:
                f.write(text.replace("\n", "\r\n").encode())

    def test_clean_merge_keeps_both_edits_and_refreshes_base(self):
        self.install_with(self.base_lines())
        self.write(self.p(EDITED), self.base_lines().replace("line 2\n", "mine 2\n"))
        new = self.base_lines().replace("line 9\n", "theirs 9\n")
        self.write(self.template(EDITED), new)
        code, out = run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        got = self.read(self.p(EDITED))
        self.assertIn("mine 2", got)
        self.assertIn("theirs 9", got)
        self.assertIn("merged      " + EDITED, out)
        self.assertEqual(self.read(self.p(".delivery/ci-install-base/" + EDITED)), new)
        # the record holds the template hash, so the next update still sees the project's lines as a change
        self.assertEqual(INS.load_state(self.tmp)[0][EDITED], INS.digest(self.template(EDITED)))
        self.assertIn("1 merged", out)
        self.assertFalse(os.path.exists(self.p(EDITED + ".new")))
        self.assertEqual(run("update", "--track", "ts", "--root", self.tmp)[0], 0)   # a second run keeps the edit
        self.assertEqual(self.read(self.p(EDITED)), got)

    def test_conflict_keeps_project_file_and_writes_markers(self):
        self.install_with(self.base_lines())
        mine = self.base_lines().replace("line 5\n", "mine 5\n")
        self.write(self.p(EDITED), mine)
        self.write(self.template(EDITED), self.base_lines().replace("line 5\n", "theirs 5\n"))
        code, out = run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read(self.p(EDITED)), mine)
        new = self.read(self.p(EDITED + ".new"))
        for mark in ("<<<<<<< project\nmine 5\n", "||||||| base\nline 5\n", "=======\ntheirs 5\n", ">>>>>>> template\n"):
            self.assertIn(mark, new)
        self.assertIn("conflict %s: 1 conflict(s); resolve %s.new, then copy it over %s and rerun update"
                      % (EDITED, EDITED, EDITED), out)
        self.assertIn("1 conflict", out)
        self.assertEqual(DOC.scripts_items(self.tmp)[0]["status"], "warn")
        self.assertIn(EDITED, DOC.scripts_items(self.tmp)[0]["detail"])

    def test_resolved_conflict_merges_on_rerun(self):
        self.install_with(self.base_lines())
        self.write(self.p(EDITED), self.base_lines().replace("line 5\n", "mine 5\n"))
        self.write(self.template(EDITED), self.base_lines().replace("line 5\n", "theirs 5\n"))
        run("update", "--track", "ts", "--root", self.tmp)
        self.write(self.p(EDITED), self.base_lines().replace("line 5\n", "both 5\n"))
        os.remove(self.p(EDITED + ".new"))
        code, out = run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)

    def test_no_base_keeps_with_plain_new_and_records_base(self):
        run("install", "--track", "ts", "--root", self.tmp)
        shutil.rmtree(self.p(".delivery/ci-install-base"))
        self.write(self.p(EDITED), "# my edit\n")
        code, out = run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read(self.p(EDITED)), "# my edit\n")
        self.assertEqual(self.read(self.p(EDITED + ".new")), self.read(self.template(EDITED)))
        self.assertIn("kept (project changes): " + EDITED, out)
        self.assertEqual(self.read(self.p(".delivery/ci-install-base/" + EDITED)), self.read(self.template(EDITED)))

    def test_crlf_project_file_merges_and_keeps_crlf(self):
        self.install_with(self.base_lines(), crlf=True)
        with open(self.p(EDITED), "wb") as f:
            f.write(self.base_lines().replace("line 2\n", "mine 2\n").replace("\n", "\r\n").encode())
        self.write(self.template(EDITED), self.base_lines().replace("line 9\n", "theirs 9\n"))
        code, out = run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        with open(self.p(EDITED), "rb") as f:
            raw = f.read()
        self.assertIn(b"mine 2\r\n", raw)
        self.assertIn(b"theirs 9\r\n", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))

    def test_unchanged_file_is_overwritten_and_base_refreshed(self):
        self.install_with(self.base_lines())
        new = self.base_lines() + "extra\n"
        self.write(self.template(EDITED), new)
        code, out = run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertIn("overwritten " + EDITED, out)
        self.assertEqual(self.read(self.p(EDITED)), new)
        self.assertEqual(self.read(self.p(".delivery/ci-install-base/" + EDITED)), new)

    def test_merge3_same_change_on_both_sides_is_not_a_conflict(self):
        text, n = INS.merge3("a\nb\nc\n", "a\nX\nc\n", "a\nX\nc\n")
        self.assertEqual((text, n), ("a\nX\nc\n", 0))


if __name__ == "__main__":
    unittest.main()
