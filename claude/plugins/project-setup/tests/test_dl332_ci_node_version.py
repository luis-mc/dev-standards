"""DL332: the CI asset takes its Node version from the project."""
import re
import unittest
from pathlib import Path

import yaml

ASSET = Path(__file__).resolve().parent.parent / "skills/claude-setup/assets/ci/dev-standards.yml"


class NodeVersion(unittest.TestCase):
    def setUp(self):
        self.text = ASSET.read_text()

    def test_yaml_parses(self):
        # Placeholders sit in plain scalars or flow lists; fill them before parsing.
        filled = re.sub(r"\{\{[A-Z_]+\}\}", "x", self.text)
        data = yaml.safe_load(filled)
        self.assertIn("checks", data["jobs"])

    def test_no_hardcoded_22(self):
        self.assertNotRegex(self.text, r"node-version:\s*['\"]?22")

    def test_node_version_file_used(self):
        self.assertIn("node-version-file:", self.text)
        for f in (".nvmrc", ".node-version", ".tool-versions", "package.json"):
            self.assertIn(f, self.text)

    def test_fallback_24(self):
        self.assertRegex(self.text, r"node-version:\s*'24'")


if __name__ == "__main__":
    unittest.main()
