"""DL228: invalid-record errors name the field, limit or rule; edit-content of decisions says the index is stale."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "project_artifacts.py"
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", CLAUDE_ARTIFACTS_NOW="2026-10-12T10:00:00+01:00")
for k in ("GIT_DIR", "GIT_WORK_TREE"):
    ENV.pop(k, None)


class RecordCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "artifacts.json").write_text("{}\n", encoding="utf-8")
        (self.root / "README.md").write_text("x\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "seed")
        self.ok("init", "--project", "Demo", "--timezone", "Europe/Lisbon", "--label", "Lisbon",
                "--windows-timezone", "GMT Standard Time", "--project-prefix", "DS")
        self.ok("feature-new", "--key", "alpha", "--title", "Alpha", "--prefix", "AL", "--apps", "plugin")

    def git(self, *a):
        subprocess.run(["git", "-C", str(self.root), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                       check=True, capture_output=True, env=ENV)

    def run_cmd(self, *a):
        a = list(a) + ([] if a[0] == "export-content" else ["--no-push"])
        r = subprocess.run([sys.executable, str(SCRIPT), *a], cwd=str(self.root), capture_output=True,
                           text=True, encoding="utf-8", env=ENV)
        return r.returncode, r.stdout, r.stderr

    def ok(self, *a):
        code, out, err = self.run_cmd(*a)
        self.assertEqual(code, 0, out + err)
        return out, err

    def export(self):
        d = self.root / "export"
        self.ok("export-content", "alpha", "--to", str(d))
        return d


class RecordMessages(RecordCase):
    def test_long_item_names_field_and_limit(self):
        code, out, err = self.run_cmd("task-add", "--owner", "alpha", "--item", "x" * 93, "--detail", "d",
                                      "--expected", "13 Oct")
        self.assertEqual(code, 1, err)
        self.assertIn("item is 93 characters; the limit is 80", err)

    def test_invalid_record_message_carries_findings(self):
        sys.path.insert(0, str(SCRIPT.parent))
        import project_artifacts as P
        msg = P.with_details("the change would make the record invalid; nothing written",
                             [("R4.8", "registry.json", "AL1: detail is longer than 600 characters")])
        self.assertIn("detail is longer than 600 characters", msg)
        self.assertTrue(msg.startswith("the change would make the record invalid"))

    def test_invalid_decision_names_entry_and_rule(self):
        d = self.export()
        dec = {"id": "D1", "question": "Q?", "status": "decided", "options": [{"id": "a", "label": "A"}],
               "chosen": "a", "decided": "2026-10-12"}
        (d / "decisions.json").write_text(json.dumps({"decisions": [dec]}), encoding="utf-8")
        code, out, err = self.run_cmd("edit-content", "alpha", "--from", str(d))
        self.assertEqual(code, 1, err)
        self.assertRegex(err.splitlines()[-1], r"D1")
        self.assertRegex(err.splitlines()[-1].lower(), r"option")

    def test_edit_content_of_decisions_prints_build_line(self):
        d = self.export()
        dec = {"id": "D1", "question": "Q?", "status": "decided", "chosen": "A", "asked": "2026-10-11",
               "decided": "2026-10-12",
               "options": [{"label": "A", "summary": "first"}, {"label": "B", "summary": "second"}]}
        (d / "decisions.json").write_text(json.dumps({"decisions": [dec]}), encoding="utf-8")
        out, err = self.ok("edit-content", "alpha", "--from", str(d))
        self.assertIn("run docs_index.py build: docs/architecture/decisions.md is now stale", out + err)


if __name__ == "__main__":
    unittest.main()
