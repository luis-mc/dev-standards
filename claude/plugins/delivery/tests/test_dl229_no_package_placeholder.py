"""DL229: no package.yml / smoke.json without a Dockerfile or a packaged-program setting (ts track)."""
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import _helpers  # noqa: F401  (puts the plugin scripts on sys.path)
import delivery_ci_install as INS

PKG = ".github/workflows/package.yml"
SMOKE = "scripts/delivery/smoke.json"
HINT = "skipped: no Dockerfile and no packaged-program setting"


def run(root, track="ts"):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = INS.main(["install", "--track", track, "--root", root])
    return code, out.getvalue() + err.getvalue()


class NoPackagePlaceholder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def p(self, rel):
        return os.path.join(self.tmp, rel)

    def write(self, rel, data):
        os.makedirs(os.path.dirname(self.p(rel)), exist_ok=True)
        with open(self.p(rel), "w", encoding="utf-8") as f:
            f.write(data)

    def test_no_dockerfile_no_package(self):
        code, out = run(self.tmp)
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(self.p(PKG)))
        self.assertFalse(os.path.exists(self.p(SMOKE)))
        self.assertIn(HINT, out)

    def test_dockerfile_installs(self):
        self.write("Dockerfile", "FROM scratch\n")
        code, out = run(self.tmp)
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(self.p(PKG)))
        self.assertNotIn(HINT, out)

    def test_configured_bundler_installs(self):
        self.write(".delivery/config.json", json.dumps({"packaged_program": {"build": "pnpm run bundle"}}))
        code, out = run(self.tmp)
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(self.p(PKG)))
        self.assertTrue(os.path.exists(self.p(SMOKE)))

    def test_configured_dockerfile_path_installs(self):
        self.write(".delivery/config.json", json.dumps({"packaged_program": {"dockerfile": "docker/App.Dockerfile"}}))
        self.write("docker/App.Dockerfile", "FROM scratch\n")
        run(self.tmp)
        self.assertTrue(os.path.exists(self.p(PKG)))

    def test_existing_package_kept(self):
        self.write(PKG, "name: Mine\n")
        code, out = run(self.tmp)
        self.assertEqual(code, 0, out)
        with open(self.p(PKG), encoding="utf-8") as f:
            self.assertEqual(f.read(), "name: Mine\n")
        self.assertIn("never deletes it", out)

    def test_template_has_guard(self):
        with open(os.path.join(INS.TEMPLATES, "ts", PKG.replace("/", os.sep)), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("id: guard", text)
        self.assertIn("[ ! -f Dockerfile ]", text)
        self.assertIn("::notice::", text)
        self.assertIn("steps.guard.outputs.skip != 'true'", text)


if __name__ == "__main__":
    unittest.main()
