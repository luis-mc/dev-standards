"""DL407: default e2e spec globs cover Cypress and pytest layouts; agent_ci base follows origin/HEAD."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "templates" / "shared" / "scripts" / "delivery"))

import agent_ci as ac  # noqa: E402
import delivery_common as dc  # noqa: E402


class E2eDefaults(unittest.TestCase):
    def test_specs(self):
        for p in ("e2e/login.spec.ts", "web/e2e/login.spec.ts", "web/cypress/login.cy.ts", "cypress/e2e/a.cy.js",
                  "tests/e2e/test_login.py", "apps/web/e2e/flows/login.spec.ts"):
            with self.subTest(p=p):
                self.assertTrue(dc.is_e2e_spec(p, {}))

    def test_not_specs(self):
        for p in ("tests/test_login.py", "src/login.test.ts", "web/src/login.ts", "tests/unit/test_x.py"):
            with self.subTest(p=p):
                self.assertFalse(dc.is_e2e_spec(p, {}))

    def test_config_wins(self):
        self.assertFalse(dc.is_e2e_spec("a.cy.ts", {"e2e_spec_paths": ["e2e/*.spec.*"]}))


class BaseDefault(unittest.TestCase):
    def setUp(self):
        self.old = Path.cwd()
        self.tmp = tempfile.TemporaryDirectory()
        import os
        os.chdir(self.tmp.name)
        subprocess.run(["git", "init", "-q"], check=True)

    def tearDown(self):
        import os
        os.chdir(self.old)
        self.tmp.cleanup()

    def test_unset(self):
        self.assertEqual(ac.settings("none.json", "none2.json")["base"], "origin/main")

    def test_main(self):
        subprocess.run(["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"], check=True)
        self.assertEqual(ac.settings("none.json", "none2.json")["base"], "origin/main")

    def test_other_name(self):
        subprocess.run(["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk"], check=True)
        self.assertEqual(ac.settings("none.json", "none2.json")["base"], "origin/trunk")

    def test_config_wins(self):
        Path("c.json").write_text('{"agent_ci": {"base": "origin/release/1"}}')
        self.assertEqual(ac.settings("c.json", "none2.json")["base"], "origin/release/1")


if __name__ == "__main__":
    unittest.main()
