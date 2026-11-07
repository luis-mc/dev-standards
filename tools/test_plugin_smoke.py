#!/usr/bin/env python3
"""Tests for tools/plugin_smoke.py on a fake plugins tree. Run: python3 -I tools/test_plugin_smoke.py"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plugin_smoke  # noqa: E402

HOOK = {"hooks": {"Stop": [{"hooks": [{"type": "command",
        "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hook.py"'}]}]}}
CLI = "import argparse\nargparse.ArgumentParser().parse_args()\n"


def make(root, name="good", **over):
    p = root / name
    (p / ".claude-plugin").mkdir(parents=True)
    (p / "scripts").mkdir()
    (p / "hooks").mkdir()
    (p / "skills" / "s1").mkdir(parents=True)
    (p / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name, "version": "1.0.0"}))
    (p / "hooks" / "hooks.json").write_text(json.dumps(HOOK))
    (p / "scripts" / "hook.py").write_text(CLI)
    (p / "skills" / "s1" / "SKILL.md").write_text("---\nname: s1\ndescription: does a thing\n---\nBody\n")
    for rel, text in over.items():
        f = p / rel
        if text is None:
            f.unlink()
        else:
            f.write_text(text)
    return p


class SmokeTest(unittest.TestCase):
    def run_one(self, **over):
        with tempfile.TemporaryDirectory() as d:
            make(Path(d), **over)
            return plugin_smoke.smoke(Path(d))["good"]

    def test_good_plugin_passes(self):
        self.assertEqual(self.run_one(), [])

    def test_missing_hook_script(self):
        fails = self.run_one(**{"scripts/hook.py": None})
        self.assertIn("hooks/hooks.json: missing script scripts/hook.py", fails)

    def test_bad_json(self):
        fails = self.run_one(**{".claude-plugin/plugin.json": "{nope"})
        self.assertTrue(any(f.startswith("plugin.json: unreadable") for f in fails))

    def test_missing_version(self):
        fails = self.run_one(**{".claude-plugin/plugin.json": '{"name": "good"}'})
        self.assertEqual(fails, ["plugin.json: no version"])

    def test_broken_py(self):
        fails = self.run_one(**{"scripts/hook.py": "def (:\n"})
        self.assertTrue(any(f.startswith("scripts/hook.py: does not compile") for f in fails))

    def test_help_failure(self):
        fails = self.run_one(**{"scripts/hook.py": "import argparse\nargparse.ArgumentParser\nraise SystemExit(3)\n"})
        self.assertTrue(any(f.startswith("scripts/hook.py: --help exit 3") for f in fails))

    def test_skill_without_front_matter(self):
        fails = self.run_one(**{"skills/s1/SKILL.md": "# no front matter\n"})
        self.assertEqual(fails, ["skills/s1/SKILL.md: no front matter"])

    def test_skill_without_description(self):
        fails = self.run_one(**{"skills/s1/SKILL.md": "---\nname: s1\n---\n"})
        self.assertEqual(fails, ["skills/s1/SKILL.md: front matter has no description"])

    def test_main_exit_codes_and_lines(self):
        with tempfile.TemporaryDirectory() as d:
            make(Path(d), "good")
            make(Path(d), "bad", **{"skills/s1/SKILL.md": "x"})
            self.assertEqual(plugin_smoke.main([d]), 1)
        with tempfile.TemporaryDirectory() as d:
            make(Path(d), "good")
            self.assertEqual(plugin_smoke.main([d]), 0)


if __name__ == "__main__":
    unittest.main()
