"""DL392: decisions-migrate fills empty option summaries; task-add warns, not refuses, for old decisions."""
import json
import unittest

from test_dl228_record_messages import RecordCase


def decision(asked, summary):
    return {"id": "D1", "question": "Q?", "status": "decided", "chosen": "A", "asked": asked, "decided": asked,
            "options": [{"label": "A", "summary": summary}, {"label": "B", "summary": "second"}]}


class Migrate(RecordCase):
    def put(self, asked, summary):
        d = self.root / "export"
        if not d.exists():
            d = self.export()
        (d / "decisions.json").write_text(json.dumps({"decisions": [decision(asked, summary)]}), encoding="utf-8")
        return d

    def read(self):
        return json.loads((self.root / "docs" / "artifacts" / "content" / "alpha" / "decisions.json").read_text("utf-8"))

    def test_task_add_warns_for_old_decision(self):
        self.ok("edit-content", "alpha", "--from", str(self.put("2026-10-01", "")))
        out, err = self.ok("task-add", "--owner", "alpha", "--item", "Thing", "--detail", "d", "--expected", "13 Oct")
        self.assertIn("decisions-migrate --feature alpha", err)

    def test_new_decision_with_empty_summary_is_still_refused(self):
        d = self.put("2026-11-20", "")
        code, out, err = self.run_cmd("edit-content", "alpha", "--from", str(d))
        self.assertEqual(code, 1, err)
        self.assertIn("summary", err)

    def test_dry_run_then_flag_then_fill(self):
        self.ok("edit-content", "alpha", "--from", str(self.put("2026-10-01", "")))
        out, err = self.ok("decisions-migrate", "--feature", "alpha", "--dry-run")
        self.assertEqual(self.read()["decisions"][0]["options"][0]["summary"], "")
        self.ok("decisions-migrate", "--feature", "alpha")
        self.assertEqual(self.read()["decisions"][0]["options"][0]["summary"], "summary missing")
        self.ok("edit-content", "alpha", "--from", str(self.put("2026-10-01", "")))
        self.ok("decisions-migrate", "--feature", "alpha", "--fill-from-title")
        self.assertEqual(self.read()["decisions"][0]["options"][0]["summary"], "A")


if __name__ == "__main__":
    unittest.main()
