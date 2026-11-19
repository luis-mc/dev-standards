"""AR70: every command that renders the record also refreshes the Full Progress publish copy (R9.12)."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_dl228_record_messages import RecordCase, SCRIPT  # noqa: E402

PLUGIN = SCRIPT.parent.parent


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class PublishCopy(RecordCase):
    def setUp(self):
        super().setUp()
        self.ok("task-add", "--owner", "alpha", "--item", "First", "--detail", "d", "--expected", "13 Oct",
                "--status", "To do")
        self.id = "AL1"

    def fp(self):
        return self.root / "docs/artifacts/full-progress.html"

    def copy(self):
        found = list((self.root / ".claude/artifacts-publish").glob("*.html"))
        self.assertEqual(len(found), 1, found)
        return found[0]

    def pending(self, *extra):
        import subprocess
        from test_dl228_record_messages import ENV
        r = subprocess.run([sys.executable, str(SCRIPT), "pending", "--json", *extra], cwd=str(self.root),
                           capture_output=True, text=True, encoding="utf-8", env=ENV)
        out = r.stdout
        return json.loads(out)

    def fp_file(self):
        m = json.loads((self.root / "docs/artifacts/manifest.json").read_text(encoding="utf-8"))
        return self.root / "docs/artifacts" / m["full_progress"]["file"]

    def same_as_copy(self):
        c = self.copy()
        meta = json.loads(Path(str(c) + ".meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["sha256"], sha(c))

    def test_copy_follows_set_task_status_and_task_add(self):
        self.ok("set-task-status", self.id, "Running", "--expected", "13 Oct ~12:00", "--no-release", "study")
        a = sha(self.copy())
        self.same_as_copy()
        self.ok("task-add", "--owner", "alpha", "--item", "Second", "--detail", "d", "--expected", "14 Oct",
                "--status", "To do")
        self.assertNotEqual(a, sha(self.copy()))
        self.same_as_copy()
        self.assertIn("Second", self.copy().read_text(encoding="utf-8"))

    def test_detail_only_change_reaches_copy_but_is_not_listed(self):
        self.ok("set-task-status", self.id, "Running", "--expected", "13 Oct ~12:00", "--no-release", "study")
        self.ok("mark-published", "full-progress", "--url", "https://example.com/a")
        before = sha(self.copy())
        self.ok("set-task-status", self.id, "Running", "--expected", "13 Oct ~12:00", "--no-release", "study", "--detail", "a brand new detail")
        self.assertIn("a brand new detail", self.copy().read_text(encoding="utf-8"))
        self.assertNotEqual(before, sha(self.copy()))
        self.assertEqual(self.pending()["artifacts"], [])        # R9.6 kept

    def test_render_wording(self):
        self.ok("set-task-status", self.id, "Running", "--expected", "13 Oct ~12:00", "--no-release", "study")
        out, _ = self.ok("render")
        self.assertNotIn("nothing to do", out)
        self.assertIn("record already rendered; publish copy is current", out)

    def test_render_says_refreshed_when_the_copy_was_old(self):
        self.ok("set-task-status", self.id, "Running", "--expected", "13 Oct ~12:00", "--no-release", "study")
        c = self.copy()
        c.unlink()
        out, _ = self.ok("render")
        self.assertIn("publish copy refreshed", out)
        self.assertTrue(self.copy().is_file())

    def test_order_in_hook_and_rule(self):
        hook = (PLUGIN / "scripts/hook_end_of_turn.py").read_text(encoding="utf-8")
        self.assertIn("1) %s pending '\n                   '--json --refresh; 2) publish the path it prints; 3) mark-published", hook)
        rule = (PLUGIN / "rules/project-artifacts.md").read_text(encoding="utf-8")
        self.assertIn("`pending --json --refresh`, publish the path it prints, then `mark-published`", rule)

    def test_task_add_warns_without_a_release_to_ride(self):
        code, out, err = self.run_cmd("task-add", "--owner", "alpha", "--item", "Loose", "--detail", "d",
                                      "--expected", "14 Oct", "--status", "To do")
        self.assertEqual(code, 0, out + err)
        self.assertIn("task-add --release", err)
        self.assertIn("--rides", err)

    def test_task_add_no_warning_with_an_open_release(self):
        self.ok("task-add", "--owner", "alpha", "--item", "Rel", "--detail", "d", "--expected", "14 Oct",
                "--status", "To do", "--release")
        code, out, err = self.run_cmd("task-add", "--owner", "alpha", "--item", "Other", "--detail", "d",
                                      "--expected", "14 Oct", "--status", "To do")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("task-add --release", err)

    def test_mark_published_still_refuses_an_older_copy(self):
        self.ok("set-task-status", self.id, "Running", "--expected", "13 Oct ~12:00", "--no-release", "study")
        reg = self.root / "docs/artifacts/registry.json"
        reg.write_text(reg.read_text(encoding="utf-8") + " ", encoding="utf-8")   # a record change no command made
        code, out, err = self.run_cmd("mark-published", "full-progress", "--url", "https://example.com/a")
        self.assertEqual(code, 1, out + err)
        self.assertIn("older than the latest record change", out + err)


if __name__ == "__main__":
    unittest.main()
