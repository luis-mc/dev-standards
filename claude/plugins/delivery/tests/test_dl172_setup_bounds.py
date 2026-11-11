"""DL172: delivery writes the hooks, .delivery/config.json and the session_guard entry; project-setup does not."""
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import _helpers  # noqa: F401
import delivery_ci_install as INS

PLUGINS = Path(__file__).resolve().parents[2]
SETUP = PLUGINS / "project-setup/skills"


def run(*argv):
    out = StringIO()
    with redirect_stdout(out), redirect_stderr(StringIO()):
        code = INS.main(list(argv))
    return code, out.getvalue()


class Bounds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def settings(self):
        return json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))

    def test_fresh_install_writes_moved_files_and_entry(self):
        code, _ = run("install", "--track", "ts", "--root", str(self.root))
        self.assertEqual(code, 0)
        for rel in (".githooks/pre-push", ".githooks/commit-msg", ".delivery/config.json", "scripts/delivery/session_guard.py"):
            self.assertTrue((self.root / rel).exists(), rel)
        cfg = json.loads((self.root / ".delivery/config.json").read_text(encoding="utf-8"))
        self.assertFalse([k for k in cfg if k.startswith("_")])
        self.assertEqual(cfg["caps"]["total"], 53)
        pre = self.settings()["hooks"]["PreToolUse"]
        self.assertEqual(len(pre), 1)
        self.assertIn("session_guard.py", pre[0]["hooks"][0]["command"])

    def test_settings_merge_keeps_other_entries_and_is_idempotent(self):
        (self.root / ".claude").mkdir()
        other = {"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "x"}]}],
                           "Stop": []}, "model": "opus"}
        (self.root / ".claude/settings.json").write_text(json.dumps(other), encoding="utf-8")
        run("install", "--track", "ts", "--root", str(self.root))
        run("update", "--track", "ts", "--root", str(self.root))
        data = self.settings()
        self.assertEqual(data["model"], "opus")
        self.assertEqual(len(data["hooks"]["PreToolUse"]), 2)
        self.assertEqual(data["hooks"]["PreToolUse"][0]["matcher"], "Edit")
        self.assertIn("Stop", data["hooks"])

    def test_bad_settings_file_is_left_alone(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude/settings.json").write_text("{nope", encoding="utf-8")
        run("install", "--track", "ts", "--root", str(self.root))
        self.assertEqual((self.root / ".claude/settings.json").read_text(encoding="utf-8"), "{nope")

    def test_update_on_old_layout_keeps_paths_and_config(self):
        (self.root / ".githooks").mkdir()
        (self.root / ".githooks/pre-push").write_text("#!/bin/sh\n# old copy\nfast_guards.py\n", encoding="utf-8")
        (self.root / ".delivery").mkdir()
        (self.root / ".delivery/config.json").write_text('{"tz": "Europe/Lisbon"}', encoding="utf-8")
        code, _ = run("update", "--track", "ts", "--root", str(self.root))
        self.assertEqual(code, 0)
        # DL201: no install record, so the old copy is kept and the new hook lands in .new
        self.assertIn("old copy", (self.root / ".githooks/pre-push").read_text(encoding="utf-8"))
        hook = (self.root / ".githooks/pre-push.new").read_text(encoding="utf-8")
        self.assertIn("train_freeze.py", hook)
        self.assertEqual(json.loads((self.root / ".delivery/config.json").read_text(encoding="utf-8")), {"tz": "Europe/Lisbon"})
        self.assertTrue((self.root / ".githooks/commit-msg").exists())

    def test_install_moves_a_foreign_pre_push_to_local(self):
        (self.root / ".githooks").mkdir()
        (self.root / ".githooks/pre-push").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        run("install", "--track", "ts", "--root", str(self.root))
        self.assertIn("echo mine", (self.root / ".githooks/pre-push.local").read_text(encoding="utf-8"))
        self.assertIn("fast_guards.py", (self.root / ".githooks/pre-push").read_text(encoding="utf-8"))

    def test_only_config_and_settings(self):
        code, _ = run("install", "--only", "config,settings", "--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertTrue((self.root / ".delivery/config.json").exists())
        self.assertTrue((self.root / ".claude/settings.json").exists())
        self.assertFalse((self.root / "scripts").exists())

    def test_project_setup_no_longer_ships_them(self):
        for rel in ("tech-stack-setup/assets/tooling/shared/.githooks/pre-push",
                    "tech-stack-setup/assets/tooling/shared/.githooks/commit-msg",
                    "claude-setup/assets/delivery-config.json"):
            self.assertFalse((SETUP / rel).exists(), rel)
        settings = (SETUP / "claude-setup/assets/.claude/settings.json").read_text(encoding="utf-8")
        self.assertNotIn("session_guard", settings)
        self.assertNotIn("PreToolUse", settings)


if __name__ == "__main__":
    unittest.main()
