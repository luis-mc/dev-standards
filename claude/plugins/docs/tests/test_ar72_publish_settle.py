"""AR72: Full Progress is published once after a burst of record changes (ARTIFACTSPEC R9.13, R9.14)."""
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_dl228_record_messages import ENV, RecordCase, SCRIPT  # noqa: E402

HOOK = SCRIPT.parent / "hook_end_of_turn.py"
sys.path.insert(0, str(SCRIPT.parent))
import artifact_hourly as H  # noqa: E402

T0 = datetime(2026, 10, 12, 10, 0, 0, tzinfo=timezone.utc)
URL = "https://example.com/a"


def at(sec):
    return (T0 + timedelta(seconds=sec)).isoformat()


class Settle(RecordCase):
    def setUp(self):
        super().setUp()
        self.ok("task-add", "--owner", "alpha", "--item", "First", "--detail", "d", "--expected", "13 Oct",
                "--status", "To do")
        self.sid = 0

    def env(self, sec):
        e = dict(ENV, CLAUDE_ARTIFACTS_NOW=at(sec))
        e.pop("CLAUDE_ARTIFACTS_SETTLE_SEC", None)
        return e

    def cmd(self, sec, *a):
        r = subprocess.run([sys.executable, str(SCRIPT), *a, *(["--no-push"] if a[0] == "set-task-status" else [])], cwd=str(self.root), capture_output=True,
                           text=True, encoding="utf-8", env=self.env(sec))
        return r

    def change(self, sec, detail, status="Running"):
        r = self.cmd(sec, "set-task-status", "AL1", status, "--expected", "13 Oct ~12:00", "--no-release",
                     "study", "--detail", detail)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def hook(self, sec):
        self.sid += 1
        r = subprocess.run([sys.executable, str(HOOK)], cwd=str(self.root), capture_output=True, text=True,
                           input=json.dumps({"cwd": str(self.root), "session_id": "s%d" % self.sid}),
                           env=self.env(sec))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def publish(self, sec):
        r = self.cmd(sec, "pending", "--json", "--refresh")
        self.assertIn(r.returncode, (0, 1), r.stderr)
        return self.cmd(sec, "mark-published", "full-progress", "--url", URL)

    def test_burst_is_asked_for_once_after_the_window(self):
        for i, sec in enumerate((0, 10, 20)):
            self.change(sec, "change %d" % i)
            out = self.hook(sec + 1)
            self.assertNotEqual(out.get("decision"), "block", out)
            self.assertIn("settling", out.get("systemMessage", ""))
        out = self.hook(20 + 70)        # quiet for 70 s
        self.assertEqual(out.get("decision"), "block", out)
        self.assertIn("Publish", out["reason"])

    def test_second_publish_inside_the_window_is_warned_and_one_after_is_not(self):
        self.change(0, "one")
        r = self.publish(5)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("previous Full Progress publish", r.stderr)    # the first publish is never warned about
        self.change(10, "two")
        r = self.publish(35)            # 30 s after the previous one
        self.assertIn("previous Full Progress publish was 30 s ago", r.stderr)
        self.change(40, "three")
        r = self.publish(35 + 90)
        self.assertNotIn("previous Full Progress publish", r.stderr)

    def test_changes_unpublished_after_the_window_are_still_asked_for(self):
        self.change(0, "one")
        self.assertTrue(self.publish(5).returncode == 0)
        self.change(30, "two", "Waiting")
        self.assertNotEqual(self.hook(40).get("decision"), "block")        # inside the window of the publish
        self.assertEqual(self.hook(100).get("decision"), "block")          # window passed: not lost

    def test_unchanged_copy_is_not_asked_for_outside_the_hourly_failsafe(self):
        self.change(0, "one")
        self.publish(5)
        self.assertEqual(self.hook(200), {})
        r = self.cmd(300, "pending", "--json", "--refresh")
        self.assertEqual(json.loads(r.stdout)["artifacts"], [])

    def test_hourly_failsafe_fires_at_60_minutes(self):
        self.change(0, "one")
        self.publish(5)
        self.assertEqual(self.hook(59 * 60), {})
        out = self.hook(61 * 60 + 10)
        self.assertEqual(out.get("decision"), "block", out)
        self.assertIn("hourly fail-safe", out["reason"])

    def test_settle_key_defaults_to_60_and_is_read_from_config(self):
        env = os.environ.pop("CLAUDE_ARTIFACTS_SETTLE_SEC", None)
        try:
            self.assertEqual(H.settle_sec(self.root), 60)
            (self.root / ".delivery").mkdir()
            cfg = self.root / ".delivery" / "config.json"
            cfg.write_text(json.dumps({"full_progress": {"settle_sec": 15}}), encoding="utf-8")
            self.assertEqual(H.settle_sec(self.root), 15)
            cfg.write_text(json.dumps({"full_progress": {"settle_sec": "x"}}), encoding="utf-8")
            self.assertEqual(H.settle_sec(self.root), 60)
        finally:
            if env is not None:
                os.environ["CLAUDE_ARTIFACTS_SETTLE_SEC"] = env


if __name__ == "__main__":
    unittest.main()
