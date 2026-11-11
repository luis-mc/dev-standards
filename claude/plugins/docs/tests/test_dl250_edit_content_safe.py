"""DL250: edit-content replaces a content folder atomically; a locked folder loses nothing."""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_dl228_record_messages import ENV, RecordCase, SCRIPT  # noqa: E402

sys.path.insert(0, str(SCRIPT.parent))
import project_artifacts as PA  # noqa: E402


def locked(*a, **k):
    raise PermissionError(13, "The process cannot access the file because it is being used (WinError 32)")


class SafeReplace(RecordCase):
    def content(self):
        return {p.name: p.read_bytes() for p in (self.root / "docs/artifacts/content/alpha").iterdir() if p.is_file()}

    def dots(self):
        return [p.name for p in (self.root / "docs/artifacts/content").iterdir() if p.name.startswith(".")]

    def edited(self, text):
        d = self.export()
        (d / "01-what-and-why.html").write_text("<!-- title: What and why -->\n<p>%s</p>\n" % text, encoding="utf-8")
        (d / "02-extra.html").write_text("<!-- title: Extra -->\n<p>extra</p>\n", encoding="utf-8")
        return d

    def inproc(self, *a):
        cwd = os.getcwd()
        os.chdir(str(self.root))
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = PA.main(list(a) + ["--no-push"])
        finally:
            os.chdir(cwd)
        return code, err.getvalue()

    def test_normal_edit_replaces_and_leaves_no_dot_folders(self):
        d = self.edited("new text")
        self.ok("edit-content", "alpha", "--from", str(d))
        self.assertIn(b"new text", self.content()["01-what-and-why.html"])
        self.assertIn("02-extra.html", self.content())
        self.assertEqual(self.dots(), [])

    def test_locked_rename_keeps_old_files_and_replaces_in_place(self):
        before = self.content()
        d = self.edited("in place")
        with mock.patch.object(PA.os, "rename", side_effect=locked):
            code, err = self.inproc("edit-content", "alpha", "--from", str(d))
        self.assertEqual(code, 0, err)
        after = self.content()
        self.assertIn(b"in place", after["01-what-and-why.html"])
        self.assertIn("meta.json", after)
        self.assertTrue(set(before) - {"01-what-and-why.html"} <= set(after))
        self.assertEqual(self.dots(), [])

    def test_locked_everything_refuses_and_keeps_all_old_files(self):
        before = self.content()
        d = self.edited("refused")
        with mock.patch.object(PA.os, "rename", side_effect=locked), \
                mock.patch.object(Path, "write_bytes", autospec=True, side_effect=locked):
            code, err = self.inproc("edit-content", "alpha", "--from", str(d))
        self.assertNotEqual(code, 0)
        self.assertEqual(self.content(), before)

    def test_locked_old_removal_is_only_a_warning(self):
        d = self.edited("warn")
        real = shutil.rmtree

        def fail_old(path, *a, **k):
            if ".old-" in str(path):
                raise PermissionError(13, "WinError 32")
            return real(path, *a, **k)
        with mock.patch.object(PA.shutil, "rmtree", side_effect=fail_old):
            code, err = self.inproc("edit-content", "alpha", "--from", str(d))
        self.assertEqual(code, 0, err)
        self.assertIn("warn", self.content()["01-what-and-why.html"].decode())
        self.assertTrue(any(".old-" in n for n in self.dots()))
        # a leftover .old folder breaks neither check nor render nor the next edit
        for cmd, extra in (("check", []), ("render", ["--no-push"])):
            r = subprocess.run([sys.executable, str(SCRIPT), cmd] + extra, cwd=str(self.root),
                               capture_output=True, text=True, env=ENV)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        shutil.rmtree(str(self.root / "export"))
        d2 = self.edited("again")
        self.ok("edit-content", "alpha", "--from", str(d2))
        self.assertEqual(self.dots(), [])

    def test_invalid_content_leaves_old_content_untouched(self):
        before = self.content()
        d = self.export()
        (d / "meta.json").write_text("{not json", encoding="utf-8")
        code, out, err = self.run_cmd("edit-content", "alpha", "--from", str(d))
        self.assertNotEqual(code, 0)
        self.assertIn("nothing written", err)
        self.assertEqual(self.content(), before)
        self.assertEqual(self.dots(), [])


if __name__ == "__main__":
    unittest.main()
