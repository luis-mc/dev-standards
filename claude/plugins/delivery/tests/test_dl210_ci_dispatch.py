"""DL210: every ci.yml template can be started by hand (workflow_dispatch)."""
import re
import unittest
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


class Dispatch(unittest.TestCase):
    def test_every_template_has_workflow_dispatch(self):
        files = sorted(TEMPLATES.glob("*/.github/workflows/ci.yml"))
        self.assertGreaterEqual(len(files), 4)
        for f in files:
            text = f.read_text(encoding="utf-8")
            self.assertRegex(text, re.compile(r"^  workflow_dispatch:", re.M), f.parts[-4])


if __name__ == "__main__":
    unittest.main()
