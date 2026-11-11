"""DL230: Playwright install differs on GitHub-hosted and self-hosted runners."""
import re
import unittest
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / "templates" / "ts" / ".github" / "workflows"
FILES = ["ci.yml", "nightly-full.yml"]


def install_lines(text):
    return [l.strip() for l in text.splitlines() if "playwright install" in l and not l.strip().startswith("#")]


class PlaywrightPoolDeps(unittest.TestCase):
    def test_no_unconditional_with_deps(self):
        for name in FILES:
            text = (WF / name).read_text(encoding="utf-8")
            for m in re.finditer(r"^.*--with-deps.*$", text, re.M):
                i = text.rfind("\n", 0, m.start())
                block = text[max(0, text.rfind("run: |", 0, m.start())):m.end()]
                self.assertIn('RUNNER_ENVIRONMENT" = "github-hosted"', block, name)

    def test_paths(self):
        for name in FILES:
            text = (WF / name).read_text(encoding="utf-8")
            hosted, rest = text.split('"github-hosted" ]; then', 1)[1].split("else", 1)
            self_hosted = rest.split("fi", 1)[0]
            self.assertIn("--with-deps chromium", hosted, name)
            self.assertNotIn("--with-deps", self_hosted, name)
            self.assertNotIn("sudo", self_hosted, name)
            self.assertIn("playwright install chromium", self_hosted, name)
            self.assertIn("POOL_BROWSERS=chromium", self_hosted, name)
            self.assertEqual(len(install_lines(text)), 2, name)


if __name__ == "__main__":
    unittest.main()
