"""DL396: agent-check --reopen puts a closed agent row back to running and logs an event."""
import contextlib
import io
import json
import unittest
from pathlib import Path

from _helpers import make_root, L


def run(root, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = L.main(["--root", str(root)] + list(argv))
    return rc, out.getvalue()


def ledger(root):
    return json.loads((Path(root) / ".delivery" / "ledger.json").read_text())


class Reopen(unittest.TestCase):
    def test_reopen_closed_row(self):
        root = make_root()
        L.update(root, lambda led: led["agents"].append(
            {"id": "a1", "task": "T1", "state": "done", "done_by": "report-not-ready", "needs_check": True}))
        rc, out = run(root, "agent-check", "T1", "--reopen", "T1")
        self.assertEqual(rc, 0)
        led = ledger(root)
        a = led["agents"][0]
        self.assertEqual((a["state"], a["needs_check"]), ("running", False))
        self.assertNotIn("done_by", a)
        self.assertTrue(any(e["kind"] == "agent.reopened" and e["ref"] == "T1" for e in led["events"]))

    def test_reopen_open_row_changes_nothing(self):
        root = make_root()
        L.update(root, lambda led: led["agents"].append({"id": "a1", "task": "T1", "state": "running"}))
        rc, out = run(root, "agent-check", "T1", "--reopen", "T1")
        self.assertEqual(rc, 0)
        self.assertIn("already open", out)
        self.assertFalse(any(e["kind"] == "agent.reopened" for e in ledger(root)["events"]))

    def test_unknown_fails(self):
        self.assertEqual(run(make_root(), "agent-check", "zz", "--reopen", "zz")[0], 1)


if __name__ == "__main__":
    unittest.main()
