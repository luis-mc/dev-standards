"""DL392: agent-check --note; agent-done and agent-check on a closed row exit 0."""
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


def agents(root):
    return json.loads((Path(root) / ".delivery" / "ledger.json").read_text())["agents"]


class AgentNote(unittest.TestCase):
    def test_check_note_stored(self):
        root = make_root()
        L.update(root, lambda led: led["agents"].append({"id": "a1", "task": "T1", "state": "running"}))
        rc, _ = run(root, "agent-check", "T1", "--note", "waiting on CI")
        self.assertEqual(rc, 0)
        self.assertEqual(agents(root)[0]["note"], "waiting on CI")


class ClosedRow(unittest.TestCase):
    def test_done_on_closed_row_exits_zero(self):
        root = make_root()
        L.update(root, lambda led: led["agents"].append({"id": "a1", "task": "T1", "state": "running"}))
        self.assertEqual(run(root, "agent-done", "a1", "--result", "ready")[0], 0)
        rc, out = run(root, "agent-done", "a1", "--result", "ready")
        self.assertEqual(rc, 0)
        self.assertIn("already closed", out)
        self.assertEqual(agents(root)[0]["state"], "done")
        rc, out = run(root, "agent-check", "a1")
        self.assertEqual(rc, 0)
        self.assertIn("already closed", out)

    def test_unknown_still_fails(self):
        root = make_root()
        self.assertEqual(run(root, "agent-done", "zz", "--result", "ready")[0], 1)

    def test_stale_flag_skips_closed_row(self):
        root = make_root()
        led = {"agents": [{"task": "T1", "id": "a1", "state": "done"}]}
        self.assertEqual(L.stale_agents(root, {"T1": "Live"}, led), [])


if __name__ == "__main__":
    unittest.main()
