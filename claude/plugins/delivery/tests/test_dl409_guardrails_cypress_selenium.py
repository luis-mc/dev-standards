"""DL409: the guardrails judge Cypress and Selenium; stack.py lists both as known."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "templates" / "shared" / "scripts" / "delivery"))
import stack  # noqa: E402
import test_guardrails as tg  # noqa: E402


def scan(files):
    root = Path(tempfile.mkdtemp())
    try:
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        return tg.scan(root, {})["results"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def hits(files, g):
    res = scan(files)
    return ["%s:%s %s" % (i["file"], i["line"], i["message"]) for i in res[g]["breaks"]]


def cfg(body):
    return {"cypress.config.ts": "export default defineConfig({ e2e: { %s } })\n" % body}


class Cypress(unittest.TestCase):
    def test_missing_default_command_timeout(self):
        self.assertTrue(any("defaultCommandTimeout" in h for h in hits(cfg("retries: 0"), "G1")))

    def test_over_limit(self):
        self.assertTrue(any("over the e2e limit" in h for h in hits(cfg("defaultCommandTimeout: 300000"), "G1")))

    def test_clean(self):
        self.assertEqual([h for h in hits(cfg("defaultCommandTimeout: 10000"), "G1") if "cypress" in h.lower()], [])

    def test_other_timeout_over(self):
        self.assertTrue(any("pageLoadTimeout" in h for h in hits(cfg("defaultCommandTimeout: 1000, pageLoadTimeout: 500000"), "G1")))

    def test_test_file_override(self):
        files = cfg("defaultCommandTimeout: 1000")
        files["cypress/e2e/a.cy.ts"] = "it('a', { defaultCommandTimeout: 999999 }, () => {})\n"
        self.assertTrue(any("a.cy.ts" in h for h in hits(files, "G1")))

    def test_retries(self):
        self.assertTrue(any("Cypress retries" in h for h in hits(cfg("retries: 2"), "G3")))
        self.assertTrue(any("Cypress retries" in h for h in hits(cfg("retries: { runMode: 1 }"), "G3")))
        self.assertEqual([h for h in hits(cfg("retries: { runMode: 0, openMode: 2 }"), "G3") if "Cypress" in h], [])

    def test_wait(self):
        f = cfg("defaultCommandTimeout: 1000")
        f["cypress/e2e/a.cy.ts"] = "it('a', () => { cy.wait(5000) })\n"
        self.assertTrue(any("a.cy.ts" in h for h in hits(f, "G4")))
        f["cypress/e2e/a.cy.ts"] = "it('a', () => { cy.wait('@api') })\n"
        self.assertEqual(hits(f, "G4"), [])


class Selenium(unittest.TestCase):
    def py(self, line):
        return {"pytest.ini": "[pytest]\ntimeout = 100\n",
                "e2e/test_a.py": "def test_a(d):\n    %s\n" % line}

    def test_webdriverwait(self):
        self.assertTrue(any("Selenium" in h for h in hits(self.py("WebDriverWait(d, 300)"), "G1")))
        self.assertEqual([h for h in hits(self.py("WebDriverWait(d, 10)"), "G1") if "Selenium" in h], [])

    def test_js(self):
        f = {"e2e/a.test.js": "await driver.wait(until.elementLocated(x), 300000)\n"}
        self.assertTrue(any("Selenium" in h for h in hits(f, "G1")))
        f = {"e2e/a.test.js": "await driver.sleep(500)\n"}
        self.assertTrue(any("a.test.js" in h for h in hits(f, "G4")))

    def test_time_sleep(self):
        self.assertTrue(any("test_a.py" in h for h in hits(self.py("time.sleep(2)"), "G4")))


class Stack(unittest.TestCase):
    def test_known(self):
        root = Path(tempfile.mkdtemp())
        try:
            (root / "cypress.config.ts").write_text("export default {}\n")
            self.assertEqual(stack.resolve(str(root), {})["cypress"]["status"], "known")
        finally:
            shutil.rmtree(root, ignore_errors=True)
        self.assertIn("selenium", stack.KNOWN)


if __name__ == "__main__":
    unittest.main()
