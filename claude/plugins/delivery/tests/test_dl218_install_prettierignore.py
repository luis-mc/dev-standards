"""DL218: the installer lists its own copies in .prettierignore when the project uses Prettier."""
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import _helpers  # noqa: F401  (puts the plugin scripts on sys.path)
import delivery_ci_install as INS

PI = ".prettierignore"


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = INS.main(list(argv))
    return code, out.getvalue() + err.getvalue()


class PrettierIgnore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def p(self, rel):
        return os.path.join(self.tmp, rel)

    def write(self, rel, data):
        with open(self.p(rel), "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))

    def read(self):
        with open(self.p(PI), "rb") as f:
            return f.read().decode("utf-8")

    def install(self, *extra):
        code, out = run("install", "--track", "ts", "--root", self.tmp, *extra)
        self.assertIn(code, (0, 3), out)
        return out

    def test_no_prettier_no_file(self):
        self.install()
        self.assertFalse(os.path.exists(self.p(PI)))

    def test_prettierrc_creates_block(self):
        self.write(".prettierrc", "{}")
        self.install()
        text = self.read()
        self.assertIn(INS.PI_BEGIN, text)
        self.assertIn(".delivery/ci-install-base/", text)
        self.assertIn("ci-install.example.json", text)
        self.assertIn("ci-shards.example.json", text)

    def test_dev_dependency_creates_block(self):
        self.write("package.json", json.dumps({"devDependencies": {"prettier": "^3"}}))
        self.install()
        self.assertIn(INS.PI_BEGIN, self.read())

    def test_other_dependency_is_not_prettier(self):
        self.write("package.json", json.dumps({"devDependencies": {"eslint": "^9"}}))
        self.install()
        self.assertFalse(os.path.exists(self.p(PI)))

    def test_rerun_is_noop(self):
        self.write(".prettierrc", "{}")
        self.install()
        first = self.read()
        out = self.install()
        self.assertEqual(first, self.read())
        self.assertNotIn(PI, out)

    def test_user_lines_kept_and_crlf_kept(self):
        self.write("prettier.config.js", "module.exports = {};")
        self.write(PI, "dist\r\ncoverage\r\n")
        self.install()
        text = self.read()
        self.assertTrue(text.startswith("dist\r\ncoverage\r\n" + INS.PI_BEGIN))
        self.assertNotIn("\n", text.replace("\r\n", ""))

    def test_block_updated_only(self):
        self.write("package.json", json.dumps({"prettier": {}}))
        self.write(PI, "dist\n")
        self.install()
        stale = self.read().replace(".delivery/ci-install-base/", "old/path/")
        self.write(PI, stale + "after\n")
        self.install()
        text = self.read()
        self.assertIn(".delivery/ci-install-base/", text)
        self.assertNotIn("old/path/", text)
        self.assertTrue(text.startswith("dist\n"))
        self.assertTrue(text.endswith("after\n"))
        self.assertEqual(text.count(INS.PI_BEGIN), 1)

    def test_example_list_change(self):
        self.write(".prettierrc.json", "{}")
        items = [("a.example.json", "", "written"), ("b.example.json", "", "written")]
        INS.prettierignore(items, self.tmp)
        self.assertIn("b.example.json", self.read())
        INS.prettierignore(items[:1], self.tmp)
        self.assertNotIn("b.example.json", self.read())
        self.assertIn("a.example.json", self.read())

    def test_dry_run_writes_nothing(self):
        self.write(".prettierrc", "{}")
        out = self.install("--dry-run")
        self.assertFalse(os.path.exists(self.p(PI)))
        self.assertIn("would be written", out)


if __name__ == "__main__":
    unittest.main()
