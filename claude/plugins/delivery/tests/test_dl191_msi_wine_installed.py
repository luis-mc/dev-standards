"""DL191: windows-msi-check.yml installs Wine only when wine or xvfb-run is missing (a pool runner has no sudo)."""
import pathlib
import re
import unittest

WF = pathlib.Path(__file__).resolve().parents[1] / "templates" / "shared" / ".github" / "workflows" / "windows-msi-check.yml"


class MsiWineInstalled(unittest.TestCase):
    def step(self):
        text = WF.read_text(encoding="utf-8")
        m = re.search(r"- name: Install Wine and a virtual display\n(.*?)(?=\n      - )", text, re.S)
        self.assertIsNotNone(m, "install step missing")
        return m.group(1)

    def test_skips_install_when_tools_present(self):
        body = self.step()
        self.assertIn("command -v wine", body)
        self.assertIn("command -v xvfb-run", body)
        self.assertIn("already installed", body)

    def test_sudo_only_in_the_else_branch(self):
        body = self.step()
        before_else, _, after_else = body.partition("else")
        self.assertNotIn("sudo", before_else)
        self.assertIn("sudo apt-get install -y --no-install-recommends wine xvfb", after_else)

    def test_names_dl191(self):
        self.assertIn("DL191", WF.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
