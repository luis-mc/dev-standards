"""DL192: rust templates - PATH in the same step, guarded targets, binaries from smoke.json, Windows deferred."""
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import _helpers  # noqa: F401
import delivery_ci_install as INS

RUST = os.path.join(INS.TEMPLATES, "rust")
CI = os.path.join(RUST, ".github", "workflows", "ci.yml")
PKG = os.path.join(RUST, ".github", "workflows", "package.yml")
WIN = INS.WINDOWS_FILES


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = INS.main(list(argv))
    return code, out.getvalue() + err.getvalue()


class PathExport(unittest.TestCase):
    def check(self, path, count):
        lines = text(path).splitlines()
        idx = [i for i, l in enumerate(lines) if 'echo "$HOME/.cargo/bin" >> "$GITHUB_PATH"' in l]
        self.assertEqual(len(idx), count)
        for i in idx:
            self.assertIn('export PATH="$HOME/.cargo/bin:$PATH"', lines[i - 1])
            self.assertNotIn("ci_tool.py", "\n".join(lines[:i - 1][-1:]))

    def test_ci(self):
        self.check(CI, 3)

    def test_package(self):
        self.check(PKG, 1)
        s = text(PKG)
        self.assertLess(s.index("export PATH="), s.index("ci_tool.py tool cargo-xwin"))


class Guards(unittest.TestCase):
    def test_codegen_and_contract_guarded(self):
        s = text(CI)
        self.assertRegex(s, r"if: \$\{\{ steps\.targets\.outputs\.codegen == 'true' \}\}\n\s+run: \|\n\s+cargo run --locked --bin codegen")
        self.assertRegex(s, r"if: \$\{\{ steps\.targets\.outputs\.contract == 'true' \}\}\n\s+run: cargo test --locked --test contract")
        self.assertIn("Skipped the codegen drift check", s)
        self.assertIn("Skipped the contract tests", s)


class Package(unittest.TestCase):
    def test_copies_come_from_smoke_json(self):
        s = text(PKG)
        self.assertNotIn("target/release/app ", s)
        self.assertNotIn("app.exe", s)
        self.assertEqual(s.count("scripts/delivery/smoke.json\"))[\"smoke\"]"), 2)
        self.assertIn('"target/release/" + n', s)
        self.assertIn("release/%s.exe", s)

    def test_windows_steps_need_the_variable(self):
        s = text(PKG)
        self.assertEqual(len(re.findall(r"if: \$\{\{ vars\.CI_WINDOWS == 'on' \}\}", s)), 2)
        self.assertIn('"${CI_WINDOWS}" = "on"', s)


class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def exists(self, rel):
        return os.path.exists(os.path.join(self.tmp, rel.replace("/", os.sep)))

    def set_windows(self, value):
        p = os.path.join(self.tmp, ".delivery", "config.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump({"ci": {"options": {"windows": value}}}, f)

    def test_skipped_when_deferred_then_installed_when_on(self):
        code, out = run("install", "--track", "rust", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        for rel in WIN:
            self.assertFalse(self.exists(rel), rel)
        self.assertTrue(self.exists(".github/workflows/package.yml"))
        self.assertIn("Windows is deferred", out)
        self.set_windows("github-hosted")
        code, out = run("install", "--track", "rust", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        for rel in WIN:
            self.assertTrue(self.exists(rel), rel)

    def test_explicit_deferred_value(self):
        self.set_windows("deferred")
        run("install", "--track", "rust", "--root", self.tmp)
        for rel in WIN:
            self.assertFalse(self.exists(rel), rel)

    def test_other_tracks_unchanged(self):
        run("install", "--track", "ts", "--root", self.tmp)
        for rel in WIN:
            self.assertTrue(self.exists(rel), rel)


if __name__ == "__main__":
    unittest.main()
